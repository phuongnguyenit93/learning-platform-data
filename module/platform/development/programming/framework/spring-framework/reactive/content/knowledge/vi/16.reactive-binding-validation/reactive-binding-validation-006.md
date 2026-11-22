# WebExchangeBindException và HandlerMethodValidationException trong Spring WebFlux

Spring WebFlux hỗ trợ Bean Validation cho dữ liệu request và method validation cho ràng buộc đặt trực tiếp trên tham số hoặc giá trị trả về của handler. Hai cơ chế có phạm vi khác nhau, vì vậy có thể phát sinh hai exception: **WebExchangeBindException** và **HandlerMethodValidationException**.

**WebExchangeBindException** thường biểu thị lỗi bind hoặc validate riêng một command object như request body, model attribute hoặc request part có @Valid/@Validated. **HandlerMethodValidationException** biểu thị lỗi validation ở cấp method, ví dụ constraint @Min hoặc @NotBlank trên tham số, hay constraint trên return value. Chỉ nhìn thấy @Valid trong chữ ký controller chưa đủ để kết luận exception nào sẽ xuất hiện.

Bài học thuộc nhóm **Binding và validation**, tập trung vào điều kiện phát sinh, dữ liệu lỗi, status HTTP, cách xử lý tập trung và kiểm thử hai exception này.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt data binding, Bean Validation và method validation.
- Xác định khi nào WebFlux phát WebExchangeBindException hoặc HandlerMethodValidationException.
- Hiểu vai trò của @Valid, @Validated, constraint trực tiếp và BindingResult.
- Đọc field errors, global errors và lỗi được nhóm theo method parameter.
- Phân biệt input violation (400) với return-value violation (500).
- Xử lý cả hai exception bằng @RestControllerAdvice.
- Cấu hình validator, message và response lỗi an toàn.
- Viết ứng dụng Java 17+ với Spring Boot WebFlux và WebTestClient để kiểm chứng hai exception.

## 2. Ba giai đoạn xử lý

Một request có thể đi qua ba giai đoạn:

1. **Đọc và chuyển đổi dữ liệu:** body, path variable, query parameter hoặc header được chuyển sang kiểu Java.
2. **Validate object:** constraint trên field/property của object được kiểm tra.
3. **Validate method:** Spring kiểm tra constraint gắn trực tiếp trên tham số hoặc giá trị trả về của handler; nested object được kiểm tra khi có cascade validation qua @Valid.

~~~text
HTTP request
     |
     v
Argument resolution / data binding
     |
     +---- JSON parse hoặc type conversion thất bại
     |          +---- lỗi đọc/bind request
     |
     v
Bean Validation trên một command object?
     +---- WebExchangeBindException
     |
     v
Method validation được kích hoạt?
     +---- HandlerMethodValidationException
~~~

Không nên gộp mọi HTTP 400 thành validation error. JSON sai cú pháp, chuyển đổi chuỗi sang số thất bại, thiếu request value và vi phạm constraint là những tình huống khác nhau. Exception cụ thể phụ thuộc bước thất bại và chữ ký handler.

## 3. WebExchangeBindException

WebExchangeBindException biểu thị lỗi binding hoặc validation trên một object được bind từ request. Class này:

- Kế thừa ServerWebInputException.
- Implement BindingResult và Errors.
- Implement ErrorResponse.
- Cung cấp field errors, global errors, object name và binding result.

Exception thường xuất hiện khi Spring validate riêng một command object được đánh dấu @Valid hoặc @Validated, chẳng hạn tham số @ModelAttribute, @RequestBody hoặc @RequestPart. Điều kiện thường gặp là tham số không phải container như Map/Collection, không có Errors hoặc BindingResult ngay sau nó, và method validation không được kích hoạt cho method.

Ví dụ:

~~~java
@PostMapping("/accounts")
public Mono<AccountResponse> create(
        @Valid @RequestBody Mono<CreateAccountRequest> request) {
    return request.map(service::create);
}
~~~

Đây là fragment cần DTO và service. Nếu field trong CreateAccountRequest vi phạm constraint, WebFlux có thể phát WebExchangeBindException. Với request body dạng Mono, lỗi xuất hiện trong quá trình xử lý reactive; controller advice vẫn có thể xử lý lỗi ở tầng web.

### Đọc lỗi từ WebExchangeBindException

Các method thường dùng:

- getAllErrors(): lấy cả global errors và field errors.
- getFieldErrors(): lấy lỗi gắn với field.
- getGlobalErrors(): lấy lỗi cấp object.
- getFieldError("name"): lấy lỗi đầu tiên của một field.
- getBindingResult(): truy cập BindingResult được wrap.
- getObjectName(): tên object được bind.
- getFieldValue("name"): giá trị field hiện tại hoặc giá trị bị từ chối trong quá trình bind.

~~~java
@ExceptionHandler(WebExchangeBindException.class)
public ResponseEntity<ApiError> handleBinding(
        WebExchangeBindException exception) {

    List<String> messages = exception.getFieldErrors().stream()
        .map(error -> error.getField() + ": " + error.getDefaultMessage())
        .toList();

    return ResponseEntity.badRequest()
        .body(new ApiError("INVALID_OBJECT", messages));
}
~~~

Đây là fragment cần khai báo ApiError và import. Khi xây response cho client, chỉ trả tên field và message đã kiểm soát. Không phản chiếu nguyên rejectedValue vì nó có thể chứa mật khẩu, token, dữ liệu cá nhân hoặc payload lớn.

## 4. HandlerMethodValidationException

HandlerMethodValidationException được bổ sung trong Spring Framework 6.1 để biểu diễn method validation trên handler method. Class này:

- Kế thừa ResponseStatusException.
- Implement MethodValidationResult và ErrorResponse.
- Có getParameterValidationResults() để lấy lỗi được nhóm theo từng method parameter.
- Có getAllErrors() để lấy danh sách lỗi tổng hợp.
- Có visitResults(Visitor) để phân loại lỗi theo loại tham số.
- Có isForReturnValue() để xác định lỗi thuộc giá trị trả về.
- Có getStatusCode() để lấy status HTTP tương ứng.

Method validation được kích hoạt khi constraint như @Min, @NotBlank, @Positive hoặc @NotNull được đặt trực tiếp trên tham số method, hoặc constraint được đặt trên method để kiểm tra return value. Khi method validation chạy, nó bao phủ cả constraint trên tham số và object lồng nhau được đánh dấu @Valid.

Ví dụ:

~~~java
@GetMapping("/search")
public Mono<List<AccountResponse>> search(
        @RequestParam @NotBlank String query,
        @RequestParam(defaultValue = "1") @Min(1) int page) {
    return service.search(query, page);
}
~~~

Đây là fragment cần service và DTO. @NotBlank và @Min gắn trực tiếp với tham số method. Nếu query trống hoặc page nhỏ hơn 1, Spring thường phát HandlerMethodValidationException.

### @Valid không tự kích hoạt method validation

@Valid là marker yêu cầu validate object lồng nhau (cascade validation). Bản thân @Valid không phải constraint annotation.

~~~java
@GetMapping("/items")
public Flux<Item> find(
        @Valid @ModelAttribute SearchCriteria criteria) {
    return service.find(criteria);
}
~~~

Chữ ký trên có thể dùng validation riêng cho command object và phát WebExchangeBindException.

Khi thêm constraint trực tiếp lên tham số:

~~~java
@GetMapping("/items")
public Flux<Item> find(
        @Valid @ModelAttribute SearchCriteria criteria,
        @RequestParam @Min(1) int page) {
    return service.find(criteria, page);
}
~~~

Constraint @Min kích hoạt method validation. Khi đó validation bao phủ cả page và object criteria được cascade qua @Valid; lỗi được báo bằng HandlerMethodValidationException.

## 5. So sánh hai exception

| Tiêu chí | WebExchangeBindException | HandlerMethodValidationException |
| --- | --- | --- |
| Phạm vi | Một object được bind/validate riêng | Toàn bộ method handler |
| Điều kiện thường gặp | @Valid/@Validated trên command object | Constraint trực tiếp trên parameter hoặc method return value |
| @Valid đơn lẻ | Có thể kích hoạt object validation | Không tự kích hoạt method validation |
| Dữ liệu lỗi | BindingResult, field errors, global errors | MethodValidationResult, parameter validation results |
| API đọc lỗi | getFieldErrors(), getGlobalErrors(), getAllErrors() | getParameterValidationResults(), getAllErrors(), visitResults() |
| Kế thừa | ServerWebInputException | ResponseStatusException |
| Status thông thường | 400 Bad Request | 400 cho input; 500 cho return-value validation |
| Có từ | Spring Framework 5.0 | Spring Framework 6.1 |

Quy tắc thực hành:

- Một @RequestBody object có @Valid, không có constraint trực tiếp khác kích hoạt method validation: thường là WebExchangeBindException.
- Một @RequestParam có @Min hoặc @NotBlank: thường là HandlerMethodValidationException.
- Một method có constraint trực tiếp trên tham số và một @Valid object: method validation có thể thay thế validation riêng; lỗi của object cũng được đưa vào HandlerMethodValidationException.
- Một method có constraint trên return value: HandlerMethodValidationException có thể báo lỗi phía server với status 500.
- Có BindingResult/Errors ngay sau tham số được validate: Spring có thể chuyển lỗi vào tham số đó để method tự xử lý theo các điều kiện của framework.

## 6. Status 400 cho input và 500 cho return value

HandlerMethodValidationException phân biệt hai loại vi phạm:

- **Input violation:** dữ liệu client cung cấp không đạt constraint; status là 400 Bad Request.
- **Return-value violation:** handler tạo ra giá trị vi phạm constraint mà server đã khai báo; status là 500 Internal Server Error.

Client chịu trách nhiệm gửi input phù hợp hợp đồng. Return value không hợp lệ là lỗi của server.

~~~java
if (exception.isForReturnValue()) {
    // Handler tạo ra kết quả vi phạm constraint: lỗi server.
} else {
    // Tham số request vi phạm constraint: lỗi client.
}

HttpStatusCode status = exception.getStatusCode();
return ResponseEntity.status(status).body(apiError);
~~~

Đừng luôn ép mọi HandlerMethodValidationException thành 400. Làm vậy có thể che dấu lỗi triển khai phía server.

## 7. BindingResult và Errors

Spring cho phép khai báo Errors hoặc BindingResult ngay sau tham số cần validate để controller tự đọc lỗi.

~~~java
@PostMapping("/accounts/manual")
public Mono<ResponseEntity<?>> createManually(
        @Valid @RequestBody CreateAccountRequest request,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return Mono.just(ResponseEntity.badRequest()
            .body("Invalid account request"));
    }

    return service.create(request)
        .map(saved -> ResponseEntity.ok(saved));
}
~~~

Đây là fragment cần service, DTO và import. Khi BindingResult đứng ngay sau tham số được validate, controller có thể được gọi cùng thông tin lỗi thay vì exception được ném ngay cho validation riêng của object. Với pattern này, request body phải được resolve trước khi gọi method; không dùng Mono<CreateAccountRequest> nếu muốn nhận BindingResult trực tiếp theo cách trên.

Với method validation, Errors/BindingResult cũng có thể được kết hợp. Tuy nhiên, controller chỉ được gọi nếu tất cả lỗi validation nằm trên các tham số có Errors ngay sau. Nếu có lỗi ở một tham số khác không được xử lý theo cách đó, Spring phát HandlerMethodValidationException.

Không đặt BindingResult ở cuối method rồi kỳ vọng nó nhận lỗi của mọi tham số. Vị trí liền kề là một phần của quy tắc argument resolution.

## 8. Đọc lỗi theo method parameter

HandlerMethodValidationException không chỉ lưu một BindingResult duy nhất. Nó cung cấp kết quả theo từng tham số:

- getParameterValidationResults(): danh sách ParameterValidationResult.
- getAllErrors(): danh sách MessageSourceResolvable tổng hợp.
- getValueResults() và getBeanResults(): phân biệt lỗi trên giá trị tham số với lỗi cascade trên object.
- getCrossParameterValidationResults(): lỗi từ constraint kiểm tra kết hợp nhiều tham số.
- visitResults(Visitor): xử lý theo loại tham số như request header, request param, model attribute hoặc nhóm khác.
- isForReturnValue(): cho biết lỗi thuộc return value.

Ví dụ đọc tổng quát:

~~~java
@ExceptionHandler(HandlerMethodValidationException.class)
public ResponseEntity<ApiError> handleMethodValidation(
        HandlerMethodValidationException exception) {

    List<String> messages = exception.getAllErrors().stream()
        .map(error -> error.getDefaultMessage() == null
            ? "Invalid value"
            : error.getDefaultMessage())
        .toList();

    return ResponseEntity.status(exception.getStatusCode())
        .body(new ApiError(
            exception.isForReturnValue()
                ? "INVALID_SERVER_RESULT"
                : "INVALID_INPUT",
            messages));
}
~~~

Khi cần response giàu ngữ cảnh hơn, dùng visitResults để xác định lỗi thuộc query parameter, header, path variable hay model attribute. Không tự suy luận tên tham số từ vị trí trong danh sách; dùng metadata MethodParameter của kết quả validation.

## 9. Xử lý tập trung bằng @RestControllerAdvice

REST API thường muốn trả response lỗi nhất quán dù exception đến từ object validation hay method validation.

~~~java
import java.util.List;
import java.util.Objects;

import org.springframework.context.MessageSourceResolvable;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiError> handleObjectValidation(
            WebExchangeBindException exception) {

        return ResponseEntity.badRequest().body(
            new ApiError("INVALID_OBJECT", messages(exception.getAllErrors())));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ApiError> handleMethodValidation(
            HandlerMethodValidationException exception) {

        HttpStatusCode status = exception.getStatusCode();
        String code = exception.isForReturnValue()
            ? "INVALID_SERVER_RESULT"
            : "INVALID_INPUT";

        return ResponseEntity.status(status).body(
            new ApiError(code, messages(exception.getAllErrors())));
    }

    private List<String> messages(
            List<? extends MessageSourceResolvable> errors) {
        return errors.stream()
            .map(error -> Objects.requireNonNullElse(
                error.getDefaultMessage(), "Invalid value"))
            .toList();
    }
}
~~~

Response model:

~~~java
import java.util.List;

public record ApiError(String code, List<String> errors) {
}
~~~

Ví dụ trên cần dependency Bean Validation provider để thực thi constraint. Hai handler có trách nhiệm riêng: object validation trả 400; method validation giữ status do Spring xác định. Ứng dụng nhiều ngôn ngữ có thể resolve message theo locale. Response chỉ chứa message đã chọn, không gửi nguyên object lỗi hoặc rejected value ra ngoài.

### ResponseEntityExceptionHandler

Spring WebFlux có ResponseEntityExceptionHandler trong package org.springframework.web.reactive.result.method.annotation. Từ Spring Framework 6.1, class này có hook để tùy biến WebExchangeBindException và HandlerMethodValidationException cùng các lỗi HTTP khác.

Dùng class này khi muốn tập trung xử lý nhiều exception chuẩn của WebFlux. Nếu chỉ cần hai response đơn giản, hai @ExceptionHandler riêng dễ đọc và đủ dùng. Đừng nhầm class reactive với ResponseEntityExceptionHandler của Spring MVC trong package servlet.

## 10. Class-level @Validated có thể đổi cơ chế

Spring Framework 6.1 bổ sung method validation tích hợp cho annotated controller. Nếu controller được đánh dấu @Validated ở cấp lớp, method validation có thể được áp dụng thông qua AOP proxy thay vì cơ chế built-in của handler adapter.

Điều này có thể làm exception và đường xử lý khác đi, ví dụ cơ chế AOP có thể phát ConstraintViolationException tùy cấu hình. Nếu muốn dùng built-in method validation của Spring WebFlux 6.1+, thông thường bỏ @Validated ở cấp controller class.

@Validated vẫn hữu ích cho validation groups trên tham số phù hợp. Cần phân biệt annotation chọn group ở parameter với việc bật AOP method validation ở cấp class. Không xóa @Validated máy móc nếu service hoặc bean khác đang dựa vào AOP validation.

## 11. Validator toàn cục, cục bộ và validation groups

Nếu Bean Validation provider có mặt trên classpath, WebFlux có thể đăng ký validator toàn cục để dùng cho @Valid và @Validated trên controller method arguments. Trong Spring Boot, dependency spring-boot-starter-validation thường cung cấp provider như Hibernate Validator.

Có thể tùy biến validator theo hai phạm vi:

- **Toàn cục:** cấu hình Validator thông qua WebFluxConfigurer.
- **Cục bộ:** dùng @InitBinder trong @Controller hoặc @ControllerAdvice để thêm validator cho data binding phù hợp.

Ví dụ cấu hình toàn cục:

~~~java
@Configuration
public class WebValidationConfig implements WebFluxConfigurer {

    private final Validator validator;

    public WebValidationConfig(Validator validator) {
        this.validator = validator;
    }

    @Override
    public Validator getValidator() {
        return validator;
    }
}
~~~

Đây là fragment; tùy Spring Boot setup, validator có thể đã được cấu hình tự động và không cần khai báo lại.

### Validation groups

Có thể áp dụng bộ quy tắc khác nhau khi tạo mới và cập nhật:

~~~java
public interface CreateChecks {
}

public interface UpdateChecks {
}

public record AccountRequest(
    @NotBlank(groups = {CreateChecks.class, UpdateChecks.class})
    String name,

    @NotBlank(groups = CreateChecks.class)
    String initialPassword
) {
}
~~~

Dùng @Validated(CreateChecks.class) ở tham số command object để chọn group. Nếu method validation được kích hoạt bởi constraint trực tiếp trên tham số, việc chọn group và phạm vi cascade cần được thiết kế nhất quán. Kiểm thử chữ ký controller thực tế thay vì giả định @Validated và @Valid luôn tạo cùng một đường xử lý.

## 12. Phân biệt validation với lỗi parse và chuyển đổi

Không phải mọi HTTP 400 đều đến từ hai exception này.

| Tình huống | Bản chất | Cách xử lý |
| --- | --- | --- |
| JSON sai cú pháp | Decoder không thể đọc body | Lỗi decoding / ServerWebInputException tương ứng |
| Query page=abc nhưng tham số là int | Chuyển đổi kiểu thất bại | Argument conversion/type mismatch |
| name="" với @NotBlank | Constraint trên object | Thường WebExchangeBindException nếu validate riêng |
| page=0 với @Min(1) trực tiếp | Method validation | HandlerMethodValidationException |
| Return value vi phạm constraint | Lỗi hợp đồng phía server | HandlerMethodValidationException, status 500 |
| Thiếu request body bắt buộc | Request input thiếu | Lỗi request binding phù hợp |

Ví dụ body:

~~~json
{"name":"Alice","age":"not-a-number"}
~~~

Nếu age trong DTO là int, JSON decoder có thể thất bại trước khi Bean Validation có object hợp lệ để kiểm tra. Ngược lại:

~~~json
{"name":"","age":15}
~~~

JSON có thể decode thành object, nhưng @NotBlank và @Min thất bại khi validation chạy. Đây là lỗi validation.

## 13. Ví dụ Java 17+ chạy được với Spring Boot WebFlux

Ví dụ hoàn chỉnh có hai endpoint:

- POST /accounts: validate request object bằng @Valid @RequestBody Mono<...>; lỗi được xử lý qua WebExchangeBindException.
- GET /accounts/search: validate query parameter bằng @NotBlank và @Min trực tiếp; lỗi được xử lý qua HandlerMethodValidationException.

### Cấu trúc project

~~~text
webflux-validation-demo/
├── pom.xml
└── src
    ├── main/java/com/example/validation
    │   ├── ValidationDemoApplication.java
    │   ├── AccountController.java
    │   ├── CreateAccountRequest.java
    │   ├── AccountResponse.java
    │   ├── ApiError.java
    │   └── ValidationAdvice.java
    └── test/java/com/example/validation
        └── AccountControllerTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>webflux-validation-demo</artifactId>
  <version>1.0.0</version>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Spring Boot 3.3.5 dùng Spring Framework 6.1.x, có HandlerMethodValidationException và built-in controller method validation. Dependency spring-boot-starter-validation cung cấp Bean Validation provider. Spring Boot quản lý các phiên bản tương thích; không cần tự đặt phiên bản Spring Framework hoặc Reactor riêng.

### ValidationDemoApplication.java

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

### CreateAccountRequest.java

~~~java
package com.example.validation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateAccountRequest(
    @NotBlank(message = "Name must not be blank")
    String name,

    @Email(message = "Email format is invalid")
    String email,

    @Min(value = 18, message = "Age must be at least 18")
    int age
) {
}
~~~

### AccountResponse.java

~~~java
package com.example.validation;

public record AccountResponse(
    String id,
    String name,
    String email,
    int age
) {
}
~~~

### ApiError.java

~~~java
package com.example.validation;

import java.util.List;

public record ApiError(
    String kind,
    List<String> errors
) {
}
~~~

### AccountController.java

~~~java
package com.example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/accounts")
public class AccountController {

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<AccountResponse> create(
            @Valid @RequestBody Mono<CreateAccountRequest> request) {

        return request.map(body ->
            new AccountResponse(
                "account-1",
                body.name(),
                body.email(),
                body.age()));
    }

    @GetMapping("/search")
    public Mono<String> search(
            @RequestParam("q") @NotBlank String query,
            @RequestParam(defaultValue = "1") @Min(1) int page) {

        return Mono.just("query=" + query + ",page=" + page);
    }
}
~~~

Không đặt class-level @Validated ở controller này. Nhờ vậy, method validation của Spring Framework 6.1+ có thể xử lý trực tiếp các constraint trên query parameter.

### ValidationAdvice.java

~~~java
package com.example.validation;

import java.util.List;
import java.util.Objects;

import org.springframework.context.MessageSourceResolvable;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiError> handleObjectValidation(
            WebExchangeBindException exception) {

        return ResponseEntity.badRequest().body(
            new ApiError("body-object", messages(exception.getAllErrors())));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ApiError> handleMethodValidation(
            HandlerMethodValidationException exception) {

        HttpStatusCode status = exception.getStatusCode();
        String kind = exception.isForReturnValue()
            ? "return-value"
            : "method-parameters";

        return ResponseEntity.status(status).body(
            new ApiError(kind, messages(exception.getAllErrors())));
    }

    private List<String> messages(
            List<? extends MessageSourceResolvable> errors) {

        return errors.stream()
            .map(error -> Objects.requireNonNullElse(
                error.getDefaultMessage(), "Invalid value"))
            .toList();
    }
}
~~~

Hai handler có chung format response nhưng giữ lại loại lỗi và status do Spring xác định. Trong production, có thể resolve message theo locale hoặc trả cấu trúc error có field/parameter rõ ràng.

### AccountControllerTests.java

~~~java
package com.example.validation;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(AccountController.class)
@Import(ValidationAdvice.class)
class AccountControllerTests {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void invalidBodyUsesWebExchangeBindException() {
        webTestClient.post()
            .uri("/accounts")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of(
                "name", "",
                "email", "not-an-email",
                "age", 15))
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.kind").isEqualTo("body-object")
            .jsonPath("$.errors").isArray();
    }

    @Test
    void invalidQueryUsesHandlerMethodValidationException() {
        webTestClient.get()
            .uri("/accounts/search?q=alice&page=0")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.kind").isEqualTo("method-parameters")
            .jsonPath("$.errors").isArray();
    }

    @Test
    void validBodyCreatesAccount() {
        webTestClient.post()
            .uri("/accounts")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of(
                "name", "Alice",
                "email", "alice@example.com",
                "age", 24))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.id").isEqualTo("account-1")
            .jsonPath("$.name").isEqualTo("Alice");
    }

    @Test
    void validQueryPassesMethodValidation() {
        webTestClient.get()
            .uri("/accounts/search?q=alice&page=2")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("query=alice,page=2");
    }
}
~~~

Chạy test tại thư mục có pom.xml:

~~~bash
mvn -q test
~~~

Nếu bốn test pass, Maven kết thúc với exit code 0. Test đầu xác minh request object đi qua WebExchangeBindException. Test thứ hai xác minh constraint trực tiếp trên query parameter đi qua HandlerMethodValidationException. Hai test còn lại kiểm tra dữ liệu hợp lệ vẫn tới handler và nhận status/body đúng.

## 14. Return-value validation và lỗi phía server

Method validation cũng có thể kiểm tra giá trị trả về của handler. Ví dụ khái quát:

~~~java
@GetMapping("/internal-code")
@NotBlank
public String internalCode() {
    return "";
}
~~~

Nếu Bean Validation và method validation áp dụng constraint return value này, giá trị rỗng vi phạm @NotBlank. HandlerMethodValidationException có thể được phát với isForReturnValue() == true và status 500. Đây là lỗi do server tạo response không đáp ứng constraint đã khai báo.

Đây là ví dụ minh họa về return constraint. Với kiểu reactive wrapper như Mono<T>, hãy kiểm tra semantics của đúng phiên bản và kiểu trả về; không tự giả định constraint đặt trên Mono<T> sẽ cascade vào giá trị T được phát. Nếu cần validate object bên trong publisher, thiết kế validator/service boundary phù hợp và kiểm thử thực tế.

## 15. Message, locale và response lỗi

Bean Validation hỗ trợ message template và message bundle:

~~~java
@NotBlank(message = "{account.name.required}")
String name;
~~~

Có thể cung cấp bundle theo locale rồi để Spring MessageSource resolve message. Spring WebFlux cũng hỗ trợ tùy biến error response của các exception thông qua message source và locale.

Một API response lỗi tốt nên:

- Có mã lỗi ổn định để client xử lý.
- Có danh sách lỗi rõ ràng, có thể gồm field hoặc parameter name.
- Dùng message phù hợp ngôn ngữ người dùng khi cần.
- Không trả stack trace, rejected value nhạy cảm hoặc dữ liệu xác thực.
- Không phụ thuộc thứ tự error nếu thứ tự không được quy định.
- Phân biệt input violation với return-value violation.

Không nên lấy exception.getMessage() rồi trả nguyên văn làm hợp đồng API. Diagnostic message có thể thay đổi giữa phiên bản hoặc chứa chi tiết nội bộ.

## 16. Lỗi thường gặp và cách khắc phục

1. **Cho rằng mọi @Valid đều tạo HandlerMethodValidationException.** @Valid tự nó không phải constraint; validation riêng của command object thường tạo WebExchangeBindException.
2. **Đặt @Min trực tiếp trên query parameter nhưng chỉ xử lý WebExchangeBindException.** Method validation có thể phát HandlerMethodValidationException; cần xử lý cả hai.
3. **Chỉ xử lý HandlerMethodValidationException và bỏ qua body validation.** Một request object có thể vẫn đi qua WebExchangeBindException.
4. **Luôn trả 400 cho HandlerMethodValidationException.** Return-value violation là lỗi server và có status 500.
5. **Nhầm lỗi JSON parse với Bean Validation.** Decoder có thể thất bại trước khi có object để validate.
6. **Đặt BindingResult không ngay sau tham số được validate.** Spring không chuyển lỗi vào tham số đó theo pattern mong muốn.
7. **Dùng BindingResult sau Mono<DTO>.** Với pattern nhận lỗi trực tiếp trong method, body phải được resolve trước; dùng command object trực tiếp và BindingResult ngay sau.
8. **Thêm class-level @Validated rồi mong built-in method validation của 6.1.** AOP validation có thể thay đổi đường exception; hiểu rõ cấu hình.
9. **Quên dependency validation provider.** Annotation constraint có thể tồn tại nhưng không có implementation validator để thực thi.
10. **Không validate nested object bằng @Valid.** Constraint ở object con không tự chạy nếu cascade validation chưa được bật.
11. **Coi @Valid và @Validated luôn giống nhau.** @Validated còn hỗ trợ validation groups.
12. **Trả rejected value vào response.** Có thể làm lộ mật khẩu, token hoặc dữ liệu cá nhân.
13. **Gom mọi lỗi vào một message chung mà mất field/parameter.** Client khó chỉ ra phần input cần sửa.
14. **Dùng thứ tự lỗi làm tiêu chí test cứng.** Thứ tự có thể thay đổi theo provider.
15. **Tạo controller validation bằng AOP mà không kiểm tra proxy.** Cơ chế AOP phụ thuộc proxy và cấu hình bean.
16. **Không phân biệt lỗi tham số với lỗi return value.** Có thể báo sai trách nhiệm client/server.
17. **Nuốt lỗi bằng onErrorResume rồi trả thành công.** Điều này che lỗi validation và làm client hiểu sai dữ liệu đã được chấp nhận.
18. **Chỉ unit test helper format lỗi.** Cần WebTestClient kiểm tra request thực sự đi vào đúng đường validation.

## 17. Checklist triển khai

- **Phiên bản:** Spring Framework có hỗ trợ HandlerMethodValidationException không? Built-in method validation có từ 6.1.
- **Provider:** dependency Bean Validation như spring-boot-starter-validation đã có chưa?
- **Object validation:** command object có @Valid/@Validated ở đúng tham số không?
- **Method validation:** constraint trực tiếp trên parameter/return value có chủ đích không?
- **Cascade:** object lồng nhau có @Valid ở vị trí cần thiết không?
- **Groups:** nếu dùng validation groups, nhóm được chọn có đúng cho create/update không?
- **BindingResult:** có đặt ngay sau tham số tương ứng và dùng kiểu body phù hợp không?
- **Class-level @Validated:** có làm method validation chuyển sang AOP ngoài dự kiến không?
- **Exception coverage:** advice xử lý cả WebExchangeBindException và HandlerMethodValidationException?
- **HTTP status:** input 400, return-value violation 500?
- **Error body:** message ổn định, có field/parameter cần thiết và không lộ rejected value?
- **Localization:** message source và locale có phù hợp yêu cầu không?
- **Parse errors:** có xử lý riêng lỗi JSON decode và type conversion không?
- **Tests:** WebTestClient chứng minh cả hai exception path và trường hợp hợp lệ?
- **Observability:** log có correlation ID, endpoint và mã lỗi mà không ghi payload nhạy cảm?

## 18. Bài tập tự kiểm tra

**Bài 1.** Một method nhận @Valid @RequestBody Mono<CreateUserRequest>; object có field @NotBlank, method không có constraint trực tiếp khác. Exception thường gặp là gì?  
**Đáp án:** WebExchangeBindException, vì đây là validation riêng trên command object.

**Bài 2.** Một method nhận @RequestParam @Min(1) int page, client gửi page=0. Exception thường gặp là gì?  
**Đáp án:** HandlerMethodValidationException, vì constraint nằm trực tiếp trên method parameter.

**Bài 3.** Vì sao @Valid đơn lẻ không tự kích hoạt method validation?  
**Đáp án:** @Valid là marker cho cascade validation, không phải constraint annotation. Constraint như @Min, @NotBlank hoặc @NotNull trên tham số mới kích hoạt method validation.

**Bài 4.** Method có @Min(1) trên query parameter và @Valid trên body DTO. Nếu body có field lỗi, exception nào có thể được phát?  
**Đáp án:** HandlerMethodValidationException, vì method validation được kích hoạt và bao phủ nested constraints qua @Valid.

**Bài 5.** HandlerMethodValidationException có luôn là HTTP 400 không?  
**Đáp án:** Không. Input violation là 400; return-value violation là 500.

**Bài 6.** WebExchangeBindException cung cấp API nào để đọc lỗi field?  
**Đáp án:** getFieldErrors(), getFieldError(...), getAllErrors() và getBindingResult().

**Bài 7.** HandlerMethodValidationException cung cấp API nào để đọc lỗi theo tham số?  
**Đáp án:** getParameterValidationResults(), getAllErrors(), getValueResults(), getBeanResults() và visitResults(...).

**Bài 8.** Một JSON body sai cú pháp có nhất thiết tạo WebExchangeBindException không?  
**Đáp án:** Không. Decoder có thể phát lỗi parse/binding trước khi Bean Validation chạy.

**Bài 9.** Có thể đặt BindingResult ở cuối danh sách tham số để nhận lỗi của mọi tham số không?  
**Đáp án:** Không. Nó phải nằm ngay sau tham số cần nhận lỗi; với method validation, các lỗi phải thỏa quy tắc Errors ngay sau của Spring.

**Bài 10.** Vì sao class-level @Validated có thể làm thay đổi exception?  
**Đáp án:** Nó có thể kích hoạt method validation qua AOP proxy thay vì built-in handler method validation của Spring Framework 6.1+.

**Bài 11.** Nếu controller trả giá trị vi phạm constraint trên return value, ai chịu trách nhiệm?  
**Đáp án:** Server; đây là return-value validation và status tương ứng là 500.

**Bài 12.** Vì sao không nên đưa FieldError.getRejectedValue() vào JSON response?  
**Đáp án:** Giá trị bị từ chối có thể chứa dữ liệu nhạy cảm; response nên chỉ tiết lộ field/message cần thiết.

## 19. Ghi nhớ

**WebExchangeBindException** đại diện cho binding hoặc validation thất bại trên một object được bind riêng. Nó kế thừa ServerWebInputException và cung cấp BindingResult, nên có thể đọc field errors và global errors. **HandlerMethodValidationException** đại diện cho validation ở cấp method handler; nó cung cấp kết quả theo từng parameter, hỗ trợ visitor và phân biệt lỗi input với lỗi return value.

Quy tắc quyết định thường gặp: @Valid trên command object, không có method constraint làm thay đổi cơ chế, dẫn tới WebExchangeBindException. Constraint trực tiếp như @Min hoặc @NotBlank trên parameter/return value kích hoạt method validation và dẫn tới HandlerMethodValidationException. @Valid có thể tham gia cascade trong method validation khi method đã được kích hoạt bởi constraint khác. Xử lý cả hai exception, giữ status 400 cho input và 500 cho return-value violation, rồi kiểm thử đường xử lý thật bằng WebTestClient.

### Tài liệu tham khảo

- Spring Framework, [WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html).
- Spring Framework, [WebFlux Request Body](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html).
- Spring Framework Javadoc, [WebExchangeBindException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html).
- Spring Framework Javadoc, [HandlerMethodValidationException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html).
- Spring Framework, [WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html).
- Spring Framework, [WebFlux Configuration and Validator](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).

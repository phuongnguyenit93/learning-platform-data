# Kiểm tra @RequestBody với @Valid và @Validated

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Binding và validation

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chuỗi xử lý từ HTTP JSON body qua message codec, object Java và Jakarta Bean Validation trong Spring WebFlux.
2. Dùng `@Valid` để kích hoạt kiểm tra DTO và kiểm tra lồng nhau; dùng `@Validated` khi cần chọn validation group.
3. Viết constraint đúng ngữ nghĩa như `@NotNull`, `@NotBlank`, `@NotEmpty`, `@Size`, `@Email`, `@Positive` và `@Pattern`.
4. Phân biệt `WebExchangeBindException` với `HandlerMethodValidationException` và lỗi đọc/giải mã request body.
5. Trả lỗi HTTP 400 có cấu trúc, đọc field errors và kiểm thử bằng `WebTestClient`.
6. Xử lý DTO lồng nhau, collection, validation groups và các trường hợp cần custom validator mà vẫn giữ reactive pipeline.

## 1. Request body được kiểm tra ở giai đoạn nào?

Khi client gửi JSON tới endpoint WebFlux, request body phải đi qua các bước:

```text
HTTP request body (JSON bytes)
          |
          v
  HttpMessageReader / codec
          |
          v
  Deserialize thành DTO Java
          |
          v
  Bean Validation (@Valid / @Validated)
          |
          +---- hợp lệ ----> Controller xử lý Mono/Flux
          |
          +---- không hợp lệ -> WebExchangeBindException
                                  |
                                  v
                              HTTP 400
```

`@RequestBody` yêu cầu WebFlux đọc body và chuyển đổi nó thành kiểu tham số bằng `HttpMessageReader`. Với JSON, codec thường dùng Jackson. Khi đã tạo được object, `@Valid` hoặc `@Validated` yêu cầu Spring áp dụng Bean Validation lên object đó.

Hai bước này có mục đích khác nhau:

- **Deserialization/binding:** JSON có đúng cú pháp và có thể chuyển thành kiểu Java mong đợi không? Ví dụ chuỗi `"abc"` có chuyển được thành `Integer` không?
- **Validation:** object đã tạo có thỏa quy tắc nghiệp vụ khai báo bằng constraint không? Ví dụ tuổi phải lớn hơn 0, email phải có định dạng phù hợp, tên không được để trống.

Nếu JSON sai cú pháp, thiếu kiểu có thể chuyển đổi hoặc có trường không thể deserialize, lỗi xảy ra **trước Bean Validation**. `@Valid` không sửa được JSON sai định dạng. Nếu object được tạo thành công nhưng vi phạm `@NotBlank` hoặc `@Positive`, đó mới là lỗi Bean Validation.

Spring WebFlux hỗ trợ `@RequestBody` với cả object trực tiếp và reactive wrapper như `Mono<T>`. Khi dùng `Mono<T>`, việc đọc body được biểu diễn trong pipeline reactive; controller có thể tiếp tục xử lý bằng `map`/`flatMap` mà không cần `block()`.

## 2. Chuẩn bị dependency và namespace

Với Spring Boot 3, Bean Validation dùng namespace **Jakarta**:

- `jakarta.validation.Valid`
- `jakarta.validation.constraints.NotBlank`
- `jakarta.validation.constraints.NotNull`
- `jakarta.validation.Validator`

Không trộn các annotation `javax.validation.*` của hệ sinh thái cũ vào dự án Boot 3.

Spring WebFlux cần có implementation Bean Validation trên classpath. Với Spring Boot, thêm `spring-boot-starter-validation` để có validator implementation, thường là Hibernate Validator:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Nếu không có Bean Validation provider, annotation có thể vẫn biên dịch vì API có mặt gián tiếp, nhưng validation không được cấu hình đầy đủ như mong đợi. Trong WebFlux, khi provider có trên classpath, Spring có thể đăng ký validator mặc định cho các controller method argument. Có thể tùy biến validator toàn cục bằng `WebFluxConfigurer` hoặc cục bộ qua `@InitBinder`.

## 3. @Valid: kích hoạt validation cho object

`@Valid` là annotation của Jakarta Bean Validation. Khi đặt trước tham số `@RequestBody`, Spring kiểm tra object được deserialize theo các constraint trên DTO:

```java
@PostMapping("/accounts")
public Mono<AccountResponse> create(
        @Valid @RequestBody Mono<CreateAccountRequest> body) {

    return body.map(request ->
            new AccountResponse(request.name(), request.email()));
}
```

Đây là **đoạn minh họa WebFlux**. `CreateAccountRequest` và `AccountResponse` là DTO do ứng dụng định nghĩa. `@Valid` yêu cầu validation object; `Mono` biểu diễn body bất đồng bộ. Khi dữ liệu không hợp lệ, pipeline body kết thúc bằng lỗi validation và controller không thực hiện phần xử lý thành công.

`@Valid` không chứa quy tắc kiểm tra riêng và cũng không phải một constraint. Nó đánh dấu cần **cascade validation** vào object. Các quy tắc cụ thể nằm ở annotation constraint như `@NotBlank`, `@Email` hoặc custom constraint.

### 3.1. Ví dụ DTO dùng Java record

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.util.List;

public record CreateAccountRequest(
        @NotBlank(message = "name is required")
        @Size(max = 80, message = "name must be at most 80 characters")
        String name,

        @NotBlank(message = "email is required")
        @Email(message = "email must be valid")
        String email,

        @NotNull(message = "age is required")
        @Positive(message = "age must be positive")
        Integer age,

        @NotNull(message = "address is required")
        @Valid
        AddressRequest address,

        @NotEmpty(message = "tags must contain at least one value")
        List<@NotBlank(message = "tag must not be blank") String> tags
) {
    public record AddressRequest(
            @NotBlank(message = "city is required")
            String city,

            @NotBlank(message = "country is required")
            String country
    ) {}
}
```

Đây là DTO hoàn chỉnh cho ví dụ. Jakarta Validation hỗ trợ annotation trên record component; Spring/Jackson có thể deserialize JSON thành record trong ứng dụng Java 17+.

`@Valid` trên `address` kích hoạt kiểm tra các constraint bên trong `AddressRequest`. Nếu bỏ `@Valid`, object address có thể được tạo nhưng các constraint `city`/`country` không được cascade từ DTO cha.

Với `tags`, `@NotEmpty` kiểm tra danh sách có ít nhất một phần tử; annotation ở type-use `List<@NotBlank String>` kiểm tra từng chuỗi không rỗng hoặc toàn khoảng trắng. Hai mức kiểm tra giải quyết hai vấn đề khác nhau.

### 3.2. Các constraint thường dùng

| Constraint | Kiểm tra | Lưu ý |
| --- | --- | --- |
| `@NotNull` | Giá trị không phải null | Không kiểm tra chuỗi rỗng hay khoảng trắng. |
| `@NotBlank` | Chuỗi không null và có ít nhất một ký tự không phải whitespace | Chỉ dành cho `CharSequence`. |
| `@NotEmpty` | Chuỗi, collection, map hoặc array không rỗng | Chuỗi chỉ chứa khoảng trắng vẫn có thể được xem là không rỗng. |
| `@Size(min, max)` | Độ dài/kích thước trong khoảng | Thông thường null được chấp nhận; ghép `@NotNull` nếu trường bắt buộc. |
| `@Email` | Định dạng email theo validator | Không xác minh mailbox tồn tại hoặc người gửi sở hữu email. |
| `@Positive` | Số lớn hơn 0 | Null hợp lệ theo semantics của constraint; ghép `@NotNull` nếu bắt buộc. |
| `@PositiveOrZero` | Số lớn hơn hoặc bằng 0 | Phù hợp với số lượng có thể bằng 0. |
| `@Min` / `@Max` | Giá trị số tối thiểu/tối đa | Dùng cho kiểu số; không thay thế kiểm tra null. |
| `@Pattern(regexp)` | Chuỗi khớp biểu thức chính quy | Null hợp lệ; ghép `@NotNull`/`@NotBlank` nếu cần. |
| `@Past` / `@Future` | Ngày/giờ trước hoặc sau hiện tại | Chú ý clock/time zone và kiểu ngày giờ sử dụng. |

Ví dụ:

- `@NotNull Integer age` chỉ bảo đảm có giá trị; `0` vẫn hợp lệ.
- `@Positive Integer age` loại 0 và số âm; nhưng nếu age là null thì constraint này không tự báo lỗi.
- `@NotBlank String name` loại null, `""` và chuỗi chỉ có whitespace.
- `@Size(max = 80) String name` giới hạn độ dài, nhưng null vẫn hợp lệ nếu không có constraint khác.

**Chọn constraint theo ý nghĩa dữ liệu.** Đừng dùng `@NotEmpty` để thay cho `@NotBlank` khi trường là tên người hoặc mã cần ký tự thực. Đừng dùng số mặc định như 0 để biểu diễn “không có dữ liệu” nếu 0 vẫn là giá trị hợp lệ.

## 4. @Validated: chọn validation group

`@Validated` thuộc Spring: `org.springframework.validation.annotation.Validated`. Trong ngữ cảnh tham số controller, nó cũng kích hoạt Bean Validation như `@Valid`, đồng thời cho phép chỉ định **validation group**.

Một DTO có thể được dùng cho nhiều thao tác. Ví dụ lúc tạo tài khoản cần kiểm tra tên bắt buộc; lúc cập nhật một phần, tên có thể không được gửi. Validation group cho phép áp dụng các bộ constraint khác nhau theo thao tác.

```java
public interface Create {}
public interface Update {}

public record AccountInput(
        @NotBlank(groups = Create.class,
                  message = "name is required when creating")
        @Size(max = 80, message = "name is too long")
        String name,

        @NotBlank(groups = {Create.class, Update.class},
                  message = "email is required")
        @Email(groups = {Create.class, Update.class},
               message = "email must be valid")
        String email
) {}
```

Trong ví dụ, `@Size` không khai báo group nên thuộc `Default`; các constraint có `groups` chỉ chạy trong group được chọn.

Để chạy cả group mặc định và group Create:

```java
@PostMapping("/accounts")
public Mono<AccountResponse> create(
        @Validated({Default.class, Create.class})
        @RequestBody Mono<AccountInput> body) {

    return body.map(input ->
            new AccountResponse(input.name(), input.email()));
}
```

Cần import `jakarta.validation.groups.Default` và Spring `Validated`. Nếu chỉ dùng `@Validated(Create.class)` thì các constraint thuộc `Default` không tự động được chạy, trừ khi group được khai báo kế thừa hoặc được đưa vào danh sách. Hãy xác định rõ nhóm nào phải chạy cho từng thao tác.

### 4.1. @Valid và @Validated nên chọn thế nào?

| Nhu cầu | Cách dùng |
| --- | --- |
| Kiểm tra DTO theo group mặc định | `@Valid @RequestBody ...` |
| Cascade validation cho object con | `@Valid` trên field/record component |
| Chọn group Create/Update cho tham số | `@Validated(Create.class)` |
| Chọn nhiều group | `@Validated({Default.class, Create.class})` |
| Kích hoạt method validation cho bean service | Có thể dùng `@Validated` ở cấp class theo cơ chế method validation/AOP phù hợp |

Trong controller, dùng `@Valid` khi chỉ cần validation mặc định; dùng `@Validated` trên tham số khi cần group. Hai annotation không phải hai cấp độ “mạnh/yếu” của cùng một kiểm tra. Chúng phục vụ hai nhu cầu khác nhau.

`@Validated` ở **cấp class** có ý nghĩa khác với `@Validated` trên tham số body: nó có thể kích hoạt method validation thông qua AOP proxy. Spring WebFlux cũng có hỗ trợ method validation cho controller method; nếu khai báo constraint trực tiếp trên tham số như `@Min`, Spring có thể kiểm tra toàn method và dùng `HandlerMethodValidationException`. Đừng thêm class-level `@Validated` theo thói quen nếu không cần AOP validation ở cấp controller/service.

## 5. WebFlux hỗ trợ @RequestBody reactive type

Trong WebFlux, `@RequestBody` có thể nhận DTO trực tiếp hoặc reactive wrapper:

```java
@PostMapping("/sync-shape")
public Mono<AccountResponse> create(
        @Valid @RequestBody CreateAccountRequest request) {
    return accountService.create(request);
}

@PostMapping("/reactive-shape")
public Mono<AccountResponse> createReactive(
        @Valid @RequestBody Mono<CreateAccountRequest> request) {
    return request.flatMap(accountService::create);
}
```

Hai method trên là **các đoạn minh họa độc lập**, không đặt cùng một mapping trong controller thực tế. `Mono<CreateAccountRequest>` phù hợp khi muốn body tham gia vào chuỗi reactive bằng `map`/`flatMap`. Cả hai cách đều có thể kích hoạt validation.

Không gọi `block()` để lấy DTO từ Mono trong controller. Cách làm như `request.block()` sẽ chặn thread và làm mất lợi ích của reactive request handling. Hãy compose xử lý bằng publisher.

### 5.1. Collection và wrapper DTO

Validation tự động ở mức method argument được thiết kế cho command object. Một container như `Map` hoặc `Collection` không được xem như một DTO đơn giản có thể tự động cascade theo cách tương tự. Nếu API nhận danh sách nhiều phần tử, nên bọc nó trong một DTO có quy tắc rõ:

```java
public record BatchCreateRequest(
        @NotEmpty(message = "items must not be empty")
        List<@Valid CreateItemRequest> items
) {}

public record CreateItemRequest(
        @NotBlank(message = "sku is required")
        String sku,

        @Positive(message = "quantity must be positive")
        int quantity
) {}
```

Đây là **đoạn minh họa**. `@Valid` trên phần tử list yêu cầu cascade tới từng `CreateItemRequest`; `@NotEmpty` kiểm tra list có phần tử. Nếu body là một stream nhiều JSON record riêng biệt (`Flux<T>`), cần thiết kế kiểm tra từng phần tử trong pipeline hoặc một wrapper phù hợp; không mặc định annotation trên container sẽ tự validate từng event theo cách mong muốn.

## 6. Lỗi validation trong WebFlux

Khi validation một command object riêng lẻ như `@Valid @RequestBody Mono<CreateAccountRequest>` thất bại, WebFlux phát `WebExchangeBindException`. Mặc định lỗi này tương ứng HTTP **400 Bad Request** và chứa `BindingResult` với danh sách lỗi field/global.

Có hai exception cần phân biệt:

| Exception | Khi nào thường xảy ra | Nội dung |
| --- | --- | --- |
| `WebExchangeBindException` | Validation riêng một tham số command object như `@RequestBody` hoặc `@ModelAttribute` | `BindingResult` cho một object, gồm field errors và global errors. |
| `HandlerMethodValidationException` | Method validation được kích hoạt bởi constraint trực tiếp trên tham số hoặc return value | Kết quả validation nhóm theo các tham số của method; có thể bao gồm nested `@Valid`. |

`@Valid` tự nó **không phải constraint annotation**, vì vậy chỉ có `@Valid` trên body object thường dẫn tới validation riêng và `WebExchangeBindException`. Nếu method có constraint trực tiếp như `@Min(1)` trên `@RequestParam` hoặc `@PathVariable`, method validation có thể áp dụng cho toàn method; khi đó lỗi body lồng nhau có thể nằm trong `HandlerMethodValidationException`.

Ứng dụng có thể cần xử lý **cả hai** exception, tùy chữ ký controller. Đừng giả định mọi lỗi liên quan @Valid đều luôn có cùng một loại exception trong mọi method signature.

### 6.1. Đọc lỗi field từ WebExchangeBindException

```java
@ExceptionHandler(WebExchangeBindException.class)
public ResponseEntity<ApiValidationError> handleBodyValidation(
        WebExchangeBindException exception) {

    List<FieldViolation> violations =
            exception.getFieldErrors().stream()
                    .map(error -> new FieldViolation(
                            error.getField(),
                            error.getDefaultMessage()))
                    .sorted(Comparator.comparing(FieldViolation::field))
                    .toList();

    return ResponseEntity.badRequest().body(
            new ApiValidationError("VALIDATION_FAILED", violations));
}
```

Đây là **đoạn minh họa trong `@RestControllerAdvice`**. `getFieldErrors()` trả lỗi gắn với từng field; `getGlobalErrors()` trả lỗi ở cấp object, chẳng hạn custom class-level constraint. `getBindingResult()` cho phép truy cập đầy đủ thông tin binding/validation.

Không nên đưa toàn bộ object request, giá trị nhạy cảm hoặc stack trace ra response lỗi. Chỉ trả tên field và message công khai đã được kiểm soát. Log nội bộ có thể chứa thêm correlation ID và exception details theo chính sách bảo mật.

### 6.2. Xử lý HandlerMethodValidationException

Khi method validation áp dụng, `HandlerMethodValidationException` chứa các kết quả được nhóm theo tham số method. Có thể:

- Dùng `ResponseEntityExceptionHandler` của WebFlux làm base class cho `@ControllerAdvice` và tùy biến response.
- Xử lý trực tiếp bằng `@ExceptionHandler(HandlerMethodValidationException.class)`.
- Duyệt `getAllValidationResults()` hoặc dùng visitor `visitResults(...)` để phân loại path variable, request parameter, request header, model attribute và các tham số khác.

Đừng ép mọi kết quả thành field name của body DTO. Một lỗi có thể nằm ở `page` query parameter hoặc header `X-Version`; response nên giữ đúng nguồn lỗi để client biết sửa request nào.

### 6.3. BindingResult ngay sau tham số

Có thể xử lý validation ngay trong controller bằng `Errors` hoặc `BindingResult`, nhưng với `@RequestBody` WebFlux, khi khai báo cách này, body phải được resolve thành object trực tiếp thay vì `Mono<T>`:

```java
@PostMapping("/accounts/local-errors")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateAccountRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body("Request validation failed");
    }

    return ResponseEntity.status(HttpStatus.CREATED)
            .body(new AccountResponse(request.name(), request.email()));
}
```

Đây là **đoạn minh họa**. `BindingResult` phải đứng ngay sau tham số được validate để Spring gắn lỗi tương ứng. Nếu body được khai báo `Mono<CreateAccountRequest>`, không dùng cách nhận `BindingResult` này; hãy để lỗi đi qua reactive pipeline và xử lý `WebExchangeBindException` trong advice hoặc bằng operator phù hợp.

## 7. Phân biệt lỗi deserialize với lỗi validation

Ví dụ cùng endpoint `/accounts`:

**Trường hợp A – JSON hợp lệ về cú pháp, nhưng vi phạm constraint:**

```json
{
  "name": " ",
  "email": "not-an-email",
  "age": -2,
  "address": {
    "city": "",
    "country": "VN"
  },
  "tags": []
}
```

Jackson có thể deserialize body thành DTO. Bean Validation sau đó báo `name`, `email`, `age`, `address.city` và `tags` không hợp lệ. Đây là validation error, thường là `WebExchangeBindException` và HTTP 400.

**Trường hợp B – JSON không thể deserialize:**

```json
{
  "name": "Lan",
  "email": "lan@example.com",
  "age": "twenty"
}
```

`age` mong đợi `Integer` nhưng JSON đưa chuỗi không chuyển đổi được. Codec/Jackson thất bại trước khi có DTO hoàn chỉnh để validate. Đây là lỗi đọc/giải mã request body, thường được biểu diễn qua exception ở nhóm `ServerWebInputException`/message decoding; không phải `@Positive` hay `@NotBlank` báo lỗi.

**Trường hợp C – thiếu body hoặc body không đúng media type:**

Nếu `@RequestBody` bắt buộc nhưng body không có, hoặc Content-Type không được hỗ trợ, request có thể bị từ chối trước Bean Validation. Kiểm tra `required`, `Content-Type` và message reader phù hợp. Đừng trả cùng một thông điệp “field invalid” cho mọi lỗi 400 nếu client cần biết họ gửi sai JSON, thiếu body hay vi phạm quy tắc field.

## 8. Chương trình Spring Boot 3.3.5 chạy được

Ví dụ dưới đây dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5**, WebFlux và Hibernate Validator qua starter validation. Controller nhận body dưới dạng `Mono`, DTO dùng record và advice chuyển lỗi field thành response JSON có cấu trúc.

Cấu trúc:

```text
webflux-request-validation/
├── pom.xml
└── src/main/java/demo/
    ├── ValidationApplication.java
    ├── CreateAccountRequest.java
    ├── AccountController.java
    └── ApiValidationAdvice.java
```

### 8.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-request-validation</artifactId>
    <version>1.0.0</version>

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
```

### 8.2. ValidationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationApplication.class, args);
    }
}
```

### 8.3. CreateAccountRequest.java

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record CreateAccountRequest(
        @NotBlank(message = "name is required")
        @Size(max = 80, message = "name must be at most 80 characters")
        String name,

        @NotBlank(message = "email is required")
        @Email(message = "email must be valid")
        String email,

        @NotNull(message = "age is required")
        @Positive(message = "age must be positive")
        Integer age,

        @NotNull(message = "address is required")
        @Valid
        Address address
) {
    public record Address(
            @NotBlank(message = "city is required")
            String city,

            @NotBlank(message = "country is required")
            String country
    ) {}
}
```

### 8.4. AccountController.java

```java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import jakarta.validation.Valid;

@RestController
public class AccountController {
    public record AccountResponse(
            String status,
            String name,
            String email) {}

    @PostMapping(
            value = "/accounts",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<AccountResponse>> create(
            @Valid @RequestBody Mono<CreateAccountRequest> body) {

        return body.map(request ->
                ResponseEntity.status(HttpStatus.CREATED).body(
                        new AccountResponse(
                                "created",
                                request.name(),
                                request.email())));
    }
}
```

### 8.5. ApiValidationAdvice.java

```java
package demo;

import java.util.Comparator;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;

@RestControllerAdvice
public class ApiValidationAdvice {
    public record FieldViolation(String field, String message) {}
    public record ApiValidationError(
            String code,
            List<FieldViolation> violations) {}

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiValidationError> handleBodyValidation(
            WebExchangeBindException exception) {

        List<FieldViolation> violations =
                exception.getFieldErrors().stream()
                        .map(error -> new FieldViolation(
                                error.getField(),
                                error.getDefaultMessage()))
                        .sorted(Comparator.comparing(FieldViolation::field))
                        .toList();

        return ResponseEntity.badRequest().body(
                new ApiValidationError("VALIDATION_FAILED", violations));
    }
}
```

### 8.6. Chạy ứng dụng

Tại thư mục có `pom.xml`:

```bash
mvn spring-boot:run
```

Gửi body hợp lệ:

```bash
curl -i -X POST http://localhost:8080/accounts \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.com","age":25,"address":{"city":"Hanoi","country":"VN"}}'
```

Kết quả thành công có status **201 Created** và body dạng:

```json
{
  "status": "created",
  "name": "Lan",
  "email": "lan@example.com"
}
```

Gửi body vi phạm constraint:

```bash
curl -i -X POST http://localhost:8080/accounts \
  -H "Content-Type: application/json" \
  -d '{"name":" ","email":"bad","age":-2,"address":{"city":"","country":"VN"}}'
```

Response có status **400 Bad Request**, body theo cấu trúc:

```json
{
  "code": "VALIDATION_FAILED",
  "violations": [
    {"field": "address.city", "message": "city is required"},
    {"field": "age", "message": "age must be positive"},
    {"field": "email", "message": "email must be valid"},
    {"field": "name", "message": "name is required"}
  ]
}
```

Danh sách được sắp xếp theo tên field trong advice để output ổn định. Các field thực tế xuất hiện phụ thuộc dữ liệu đầu vào và constraint nào bị vi phạm. Nếu thêm constraint cho address hoặc age, response sẽ có thêm violation tương ứng.

Gửi JSON sai kiểu:

```bash
curl -i -X POST http://localhost:8080/accounts \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.com","age":"twenty","address":{"city":"Hanoi","country":"VN"}}'
```

Request thất bại ở bước deserialize; không được xử lý như một lỗi `@Positive`. Response mặc định vẫn là 4xx, nhưng nội dung exception thuộc nhóm đọc/giải mã body. Nếu API cần một error contract đồng nhất, hãy bổ sung handler cho lỗi input/decoding một cách riêng biệt.

## 9. Kiểm thử bằng WebTestClient

`WebTestClient` kiểm tra HTTP contract của WebFlux mà không cần gọi controller bằng tay. Ví dụ sau nằm trong tệp test riêng và cần dependency `spring-boot-starter-test` ở scope test.

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AccountControllerTest {
    @Autowired
    WebTestClient client;

    @Test
    void validBodyCreatesAccount() {
        client.post()
                .uri("/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Lan",
                          "email": "lan@example.com",
                          "age": 25,
                          "address": {
                            "city": "Hanoi",
                            "country": "VN"
                          }
                        }
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.status").isEqualTo("created")
                .jsonPath("$.name").isEqualTo("Lan");
    }

    @Test
    void invalidBodyReturnsFieldErrors() {
        client.post()
                .uri("/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": " ",
                          "email": "bad",
                          "age": -2,
                          "address": {
                            "city": "",
                            "country": "VN"
                          }
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_FAILED")
                .jsonPath("$.violations").isArray()
                .jsonPath("$.violations[0].field")
                    .isEqualTo("address.city");
    }
}
```

Chạy test:

```bash
mvn test
```

Test xác nhận hai hợp đồng quan trọng: body hợp lệ trả 201 và body vi phạm constraint trả 400 với danh sách lỗi. Không nên chỉ kiểm tra controller method có được gọi hay không; hãy kiểm tra HTTP status và JSON response mà client thật sự nhận.

## 10. Custom validator và quy tắc nghiệp vụ

Bean Validation phù hợp với các quy tắc kiểm tra object đồng bộ: bắt buộc, độ dài, định dạng, khoảng giá trị, quan hệ đơn giản giữa các field. Khi cần quy tắc phức tạp hơn, có thể tạo annotation constraint riêng và một `ConstraintValidator`.

Ví dụ khái niệm:

```java
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = SupportedCodeValidator.class)
public @interface SupportedCode {
    String message() default "code is not supported";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Đây là **khung annotation minh họa**, cần import các kiểu Jakarta Validation và định nghĩa `SupportedCodeValidator`. Validator có thể kiểm tra quy tắc định dạng hoặc danh sách giá trị cục bộ. Tránh gọi database hoặc HTTP đồng bộ trong `isValid`: validator Bean Validation là API đồng bộ, không phải reactive publisher. Nếu quy tắc cần truy vấn tồn kho, kiểm tra username đã tồn tại hoặc gọi dịch vụ bên ngoài, hãy thực hiện ở service layer bằng `Mono/Flux` sau khi request DTO đã qua validation cấu trúc.

Ví dụ kiểm tra username tồn tại:

```java
return body.flatMap(request ->
        accountRepository.existsByEmail(request.email())
                .flatMap(exists -> exists
                        ? Mono.error(new EmailAlreadyUsedException())
                        : accountService.create(request)));
```

Đây là **đoạn minh họa**; repository và service cần trả publisher reactive. Quy tắc này phụ thuộc dữ liệu hiện tại nên xử lý bất đồng bộ trong pipeline, có thể trả conflict 409 theo API contract. `@Email` chỉ kiểm tra hình thức email, không kiểm tra email đã được đăng ký.

### 10.1. Validation không thay thế bảo mật

Không dùng validation để thay thế authentication/authorization. Một trường `role` có thể hợp lệ về cú pháp nhưng người dùng không được phép tự chọn quyền đó. Kiểm tra quyền phải dựa trên principal đã xác thực và chính sách server-side. Tương tự, giới hạn độ dài hoặc định dạng không thay thế việc chống injection, giới hạn kích thước request body, rate limit hay kiểm soát upload.

### 10.2. Validation không đảm bảo dữ liệu không đổi sau khi kiểm tra

Một DTO hợp lệ tại thời điểm nhận request không đảm bảo trạng thái database vẫn hợp lệ khi ghi. Ví dụ hai request đồng thời có thể cùng vượt qua kiểm tra “email chưa tồn tại” trước khi một request ghi dữ liệu. Ràng buộc unique trong database và xử lý xung đột vẫn cần thiết. Bean Validation là lớp kiểm tra đầu vào, không phải cơ chế transaction hay khóa dữ liệu.

## 11. Tùy biến Validator trong WebFlux

Nếu ứng dụng cần validator toàn cục tùy chỉnh, triển khai `WebFluxConfigurer`:

```java
@Configuration
public class ValidationConfig implements WebFluxConfigurer {
    private final Validator validator;

    public ValidationConfig(Validator validator) {
        this.validator = validator;
    }

    @Override
    public Validator getValidator() {
        return validator;
    }
}
```

Đây là **đoạn minh họa cấu hình**; `Validator` ở đây là Spring validation abstraction hoặc Jakarta-backed implementation tùy cấu hình dự án. Khi chỉ cần thêm một validator cục bộ cho controller hoặc advice, có thể dùng `@InitBinder` và `WebDataBinder.addValidators(...)`.

Đừng tự tạo một `ValidatorFactory` mới cho mỗi request. Validator thường được quản lý ở cấp application context và tái sử dụng; custom validator phải an toàn khi được gọi đồng thời nếu bean được dùng chung.

## 12. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Quên `spring-boot-starter-validation` | Không có Bean Validation provider phù hợp | Thêm starter validation và kiểm tra dependency runtime. |
| Dùng `javax.validation.*` trong Boot 3 | Không khớp Jakarta namespace | Dùng `jakarta.validation.*`. |
| Nghĩ `@Valid` tự định nghĩa quy tắc | Không có constraint nào để kiểm tra | Thêm `@NotBlank`, `@Email`, `@Positive` hoặc custom constraint. |
| Chỉ dùng `@Positive` cho field bắt buộc | Null vẫn có thể hợp lệ | Ghép `@NotNull` nếu null không được chấp nhận. |
| Dùng `@NotEmpty` cho tên người | Chuỗi khoảng trắng vẫn có thể qua | Dùng `@NotBlank`. |
| Quên `@Valid` trên object con | Constraint lồng nhau không được cascade | Đặt `@Valid` trên field/record component. |
| Nghĩ `@Valid` và `@Validated` là hai mức mạnh yếu | Chọn annotation không đúng mục tiêu | `@Valid` cho validation mặc định; `@Validated` cho group và Spring validation use cases. |
| Chọn group Create nhưng quên Default | Constraint thuộc Default không chạy | Thêm `Default.class` hoặc thiết kế group inheritance rõ. |
| Nghĩ mọi lỗi request body đều là WebExchangeBindException | Lỗi JSON decode bị phân loại sai | Phân biệt binding/validation với decoding/input exception. |
| Đặt constraint trực tiếp trên tham số nhưng chỉ handle WebExchangeBindException | Method validation có thể ném HandlerMethodValidationException | Xử lý cả hai exception theo chữ ký method. |
| Dùng `@Valid` trên `Mono<List<T>>` và nghĩ mọi phần tử chắc chắn tự validate | Container không phải command object thông thường | Dùng wrapper DTO có `@Valid` cho phần tử hoặc validate từng item trong pipeline. |
| Dùng BindingResult sau `Mono<T>` body | Không đúng cách resolve body và errors trong WebFlux | Dùng body object trực tiếp với BindingResult ngay sau, hoặc reactive Mono và exception handler. |
| Gọi `block()` trong controller để lấy DTO | Chặn thread xử lý reactive request | Dùng `map`/`flatMap` và return publisher. |
| Thực hiện truy vấn DB trong ConstraintValidator | Validator đồng bộ có thể chặn event-loop | Chuyển kiểm tra phụ thuộc I/O vào service reactive. |
| Trả stack trace hoặc toàn bộ request trong lỗi 400 | Rò rỉ thông tin nội bộ/nhạy cảm | Chỉ trả field và message công khai, log nội bộ có kiểm soát. |
| Nghĩ @Email xác nhận địa chỉ tồn tại | Constraint chỉ kiểm tra hình thức | Xác minh ownership bằng quy trình xác nhận email nếu nghiệp vụ cần. |
| Nghĩ DTO hợp lệ đồng nghĩa database chắc chắn nhận được | Race condition/constraint database vẫn có thể xảy ra | Giữ unique constraint và xử lý xung đột ở persistence layer. |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `@Valid @RequestBody Mono<CreateAccountRequest> body` làm những việc gì?  
**Đáp án:** WebFlux đọc body qua message reader, deserialize thành DTO, áp dụng Bean Validation lên object rồi đưa kết quả vào pipeline Mono. Nếu object vi phạm constraint, pipeline báo validation error thay vì chạy nhánh xử lý thành công.

**Câu 2.** `@Valid` có tự kiểm tra email hợp lệ không?  
**Đáp án:** Không. `@Valid` kích hoạt validation/cascade; cần `@Email` trên field email để kiểm tra định dạng.

**Câu 3.** Khác biệt chính giữa `@Valid` và `@Validated(Create.class)`?  
**Đáp án:** `@Valid` kích hoạt validation mặc định và cascade. `@Validated` là annotation Spring, có thể chọn group Create để chỉ chạy các constraint thuộc group đó.

**Câu 4.** `@Positive Integer age` có từ chối null không?  
**Đáp án:** Không nhất thiết. Ghép `@NotNull` nếu age bắt buộc phải có.

**Câu 5.** Lỗi validation của một body DTO riêng lẻ trong WebFlux thường là exception nào?  
**Đáp án:** `WebExchangeBindException`, mặc định ánh xạ HTTP 400 Bad Request.

**Câu 6.** Khi method có `@Min(1)` trực tiếp trên tham số query, validation có thể dùng exception nào?  
**Đáp án:** `HandlerMethodValidationException` vì Spring áp dụng method validation cho toàn method, có thể bao gồm cả constraint lồng qua `@Valid`.

**Câu 7.** JSON gửi `"age": "twenty"` trong khi DTO khai báo Integer là lỗi gì?  
**Đáp án:** Lỗi deserialize/binding xảy ra trước Bean Validation. `@Positive` chưa có object Integer hợp lệ để kiểm tra.

**Câu 8.** Vì sao không nên dùng database query bên trong `ConstraintValidator.isValid()`?  
**Đáp án:** Bean Validation là API đồng bộ; query blocking có thể chặn thread WebFlux. Hãy dùng service layer và compose publisher reactive cho quy tắc cần I/O.

**Câu 9.** Muốn kiểm tra các constraint trong Address DTO lồng bên trong request, cần gì?  
**Đáp án:** Đặt `@Valid` trên field/record component address; nếu address cũng bắt buộc, ghép `@NotNull`.

**Câu 10.** Với `@Validated(Create.class)`, các constraint thuộc group Default có tự chạy không?  
**Đáp án:** Không tự động. Thêm `Default.class` vào danh sách group hoặc thiết kế group kế thừa Default.

## Ghi nhớ

- **`@RequestBody` deserialize trước, Bean Validation chạy sau.** JSON sai kiểu/cú pháp là lỗi decode; object được tạo nhưng vi phạm constraint là lỗi validation.
- **`@Valid` kích hoạt validation và cascade**, còn constraint như `@NotBlank`, `@Email`, `@Positive` định nghĩa quy tắc cụ thể.
- **`@Validated` cho phép chọn validation group** như Create/Update; chú ý group Default không tự chạy nếu bạn chỉ chọn một group khác.
- Với body DTO riêng lẻ, WebFlux thường ném `WebExchangeBindException` và trả HTTP 400. Nếu method-level constraints được kích hoạt, xử lý thêm `HandlerMethodValidationException`.
- Dùng `Mono<DTO>` để giữ body trong reactive pipeline; không `block()`. Với `BindingResult`, đặt ngay sau tham số body trực tiếp; WebFlux không dùng cách đó với `Mono<T>`.
- Dùng custom constraint cho quy tắc đồng bộ. Kiểm tra cần database/HTTP nên nằm trong service reactive; validation không thay thế authorization, transaction hoặc database constraints.

### Tài liệu tham khảo

1. [Spring Framework 6.2 – WebFlux Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html): validation ở cấp tham số và method, `WebExchangeBindException`, `HandlerMethodValidationException`.
2. [Spring Framework 6.2 – @RequestBody trong WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): reactive body, `@Valid`/`@Validated` và `BindingResult`.
3. [Spring Boot – Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): Bean Validation provider, `spring-boot-starter-validation` và method validation.
4. [Spring Framework – Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): constraint, groups và custom validator.
5. [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): hợp đồng annotation, group, cascade và `ConstraintValidator`.
6. [Spring Framework 6.2 – WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): RFC 9457, `ProblemDetail` và xử lý lỗi HTTP.

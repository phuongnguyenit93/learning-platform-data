# Áp dụng validation rõ ràng trong handler

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Endpoint hàm

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao WebFlux functional endpoint cần chủ động gọi validator sau khi giải mã request body thành object.
2. Dùng `org.springframework.validation.Validator`, `SmartValidator`, `Errors` và `BeanPropertyBindingResult` để kiểm tra DTO ngay trong `HandlerFunction`.
3. Phân biệt validation dữ liệu với việc deserialize JSON, binding request parameter và kiểm tra quy tắc nghiệp vụ cần I/O.
4. Trả HTTP 400 có cấu trúc hoặc ném `ServerWebInputException` để WebFlux xử lý lỗi đầu vào.
5. Tích hợp Jakarta Bean Validation qua `LocalValidatorFactoryBean`, dùng constraint, cascade và validation group trong handler.
6. Giữ pipeline reactive, không `block()`, không gọi `subscribe()` lồng nhau và không truy vấn database đồng bộ bên trong validator.
7. Kiểm thử cả request hợp lệ, request vi phạm constraint, body rỗng và JSON sai bằng `WebTestClient`.

## 1. Vì sao functional endpoint phải gọi validator rõ ràng?

WebFlux có hai programming model phổ biến: annotated controller với `@RestController`/`@RequestBody`, và functional endpoint với `RouterFunction`/`HandlerFunction`. Với functional endpoint, ứng dụng tự viết hàm nhận `ServerRequest` và trả `Mono<ServerResponse>`.

Khi đọc JSON body, `ServerRequest.bodyToMono(CreateProductRequest.class)` chỉ yêu cầu message reader/codec giải mã body thành object. Nó không tự suy ra toàn bộ quy tắc nghiệp vụ từ các annotation trên DTO rồi tự gọi validation như cơ chế argument validation của annotated controller.

Vì vậy, handler cần gọi validator sau khi đã có object:

```text
HTTP JSON bytes
      |
      v
request.bodyToMono(CreateProductRequest.class)
      |
      v
Jackson / HttpMessageReader deserialize
      |
      v
CreateProductRequest
      |
      v
Validator.validate(object, errors)
      |
      +---- errors rỗng ----> service reactive ----> ServerResponse 2xx
      |
      +---- có errors ------> ServerResponse 400
```

**Thứ tự này rất quan trọng:** chỉ validate object sau khi decode thành công. JSON sai cú pháp hoặc không chuyển đổi được sang kiểu Java sẽ phát lỗi từ codec trước khi handler có DTO để kiểm tra. Validation không sửa JSON và không thay thế quá trình deserialize.

Trong annotated controller, Spring có thể tự kích hoạt validation cho command object qua `@Valid`/`@Validated` trên method argument. Trong WebFlux.fn, `@Valid` đặt trên một biến hay DTO không tự gọi validator. Chính handler phải thực hiện bước validation một cách tường minh.

## 2. Ba khái niệm cần tách biệt

| Công việc | Câu hỏi cần trả lời | API thường dùng |
| --- | --- | --- |
| Deserialize | JSON có thể chuyển thành kiểu Java mong muốn không? | `request.bodyToMono(Type.class)`, HttpMessageReader/codec |
| Validate DTO | Object đã tạo có thỏa constraint không? | `Validator.validate(object, errors)` hoặc Jakarta `Validator.validate(object)` |
| Kiểm tra nghiệp vụ phụ thuộc I/O | SKU đã tồn tại trong database chưa? Người dùng có quyền tạo bản ghi không? | Service/repository reactive bằng `Mono`/`Flux` |

Ví dụ:

- `"price": "many"` trong khi Java mong đợi `BigDecimal` là lỗi deserialize.
- `"price": -5` có thể deserialize thành công nhưng vi phạm quy tắc giá dương.
- Giá dương nhưng SKU đã tồn tại là lỗi nghiệp vụ cần truy vấn persistence layer.

Không gộp ba loại lỗi thành một validator đồng bộ duy nhất. Việc tách rõ giúp chọn status HTTP, thông điệp và cách xử lý phù hợp.

## 3. Spring Validator và BeanPropertyBindingResult

Spring cung cấp interface `org.springframework.validation.Validator`:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

- `supports(clazz)` cho biết validator có xử lý loại object đó không.
- `validate(target, errors)` kiểm tra object và ghi lỗi vào `Errors`.
- `Errors`/`BindingResult` lưu lỗi theo field hoặc lỗi cấp object.
- `BeanPropertyBindingResult` tạo một vùng chứa lỗi gắn với object, có hỗ trợ tên property như `name` hoặc `address.city`.

Mẫu cốt lõi trong handler:

```java
Errors errors = new BeanPropertyBindingResult(requestDto, "requestDto");
validator.validate(requestDto, errors);

if (errors.hasErrors()) {
    // Tạo HTTP 400 hoặc ném lỗi đầu vào.
}
```

`BeanPropertyBindingResult` cần object có thể truy cập thuộc tính theo JavaBean property conventions. Với ví dụ bên dưới, DTO dùng getter/setter để binding và lấy lỗi field ổn định.

### 3.1. Tạo custom Spring Validator

Ví dụ validator cho yêu cầu tạo sản phẩm:

```java
@Component
public class CreateProductValidator implements Validator {
    @Override
    public boolean supports(Class<?> clazz) {
        return CreateProductRequest.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        CreateProductRequest request = (CreateProductRequest) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "name", "name.required", "name is required");

        if (request.getPrice() == null) {
            errors.rejectValue(
                    "price", "price.required", "price is required");
        } else if (request.getPrice().signum() <= 0) {
            errors.rejectValue(
                    "price", "price.positive",
                    "price must be greater than zero");
        }
    }
}
```

Đây là **đoạn minh họa**, giả sử `CreateProductRequest` có getter `getName()` và `getPrice()`. `ValidationUtils.rejectIfEmptyOrWhitespace` là helper tiện dụng cho chuỗi bắt buộc. `errors.rejectValue` ghi lỗi vào đúng field; handler có thể lấy danh sách bằng `getFieldErrors()` hoặc `getAllErrors()`.

Custom validator nên tập trung vào quy tắc đồng bộ, nhẹ và xác định: chuỗi không rỗng, giá trị nằm trong khoảng, định dạng nội bộ hoặc quan hệ đơn giản giữa field. Không gọi database, HTTP client hay `block()` trong `validate`.

### 3.2. Lỗi field và lỗi cấp object

Có hai loại lỗi chính:

- **Field error:** gắn với một property cụ thể, ví dụ `name`, `price` hoặc `address.city`.
- **Object/global error:** quy tắc liên quan nhiều field hoặc toàn bộ object, ví dụ `startDate` phải trước `endDate`.

`errors.getFieldErrors()` chỉ lấy field errors. `errors.getGlobalErrors()` lấy lỗi cấp object. Nếu API cần phản ánh đầy đủ, dùng `errors.getAllErrors()` và biểu diễn global error bằng một định danh như `"$"` hoặc `"_global"`.

Không nên trả rejected value một cách mặc định. Giá trị đầu vào có thể chứa mật khẩu, token, thông tin cá nhân hoặc dữ liệu nhạy cảm. Response lỗi thường chỉ cần field path và message đã được kiểm soát.

## 4. Đưa validation vào HandlerFunction

Một functional handler có dạng:

```java
Mono<ServerResponse> create(ServerRequest request)
```

Để kiểm tra body, handler đọc publisher rồi gọi validator trong `flatMap` hoặc `doOnNext`. Hai cách phổ biến:

### 4.1. Ném ServerWebInputException để WebFlux xử lý 400

Đây là mẫu ngắn theo tài liệu Spring:

```java
public Mono<ServerResponse> create(ServerRequest request) {
    Mono<CreateProductRequest> body =
            request.bodyToMono(CreateProductRequest.class)
                    .doOnNext(this::validate);

    return body.flatMap(productService::create)
            .flatMap(product ->
                    ServerResponse.ok().bodyValue(product));
}

private void validate(CreateProductRequest input) {
    Errors errors =
            new BeanPropertyBindingResult(input, "createProductRequest");

    validator.validate(input, errors);

    if (errors.hasErrors()) {
        throw new ServerWebInputException(errors.toString());
    }
}
```

Đây là **đoạn minh họa**; `productService.create` cần trả publisher reactive. Khi `validate` ném `ServerWebInputException`, exception trở thành lỗi của reactive chain và WebFlux ánh xạ lỗi đầu vào thành HTTP 400.

Ưu điểm là ít code và hợp với xử lý lỗi tập trung. Hạn chế là `errors.toString()` không phải error contract JSON ổn định mà client nên phụ thuộc. Nếu API cần cấu trúc lỗi riêng, có thể chuyển errors thành response trực tiếp hoặc xây dựng cơ chế xử lý lỗi tập trung.

### 4.2. Tạo response 400 có cấu trúc ngay trong handler

Nếu muốn kiểm soát body lỗi cho từng functional endpoint, có thể kiểm tra `Errors` và trả `ServerResponse.badRequest()`:

```java
return request.bodyToMono(CreateProductRequest.class)
        .flatMap(input -> {
            Errors errors =
                    new BeanPropertyBindingResult(input, "createProductRequest");
            validator.validate(input, errors);

            if (errors.hasErrors()) {
                return ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(toApiError(errors));
            }

            return productService.create(input)
                    .flatMap(product ->
                            ServerResponse.status(HttpStatus.CREATED)
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .bodyValue(product));
        });
```

Đây là **đoạn minh họa**. `toApiError` chuyển `Errors` sang DTO response. Nhánh thành công chỉ chạy khi không còn lỗi. Cả hai nhánh đều trả `Mono<ServerResponse>`, nên toàn bộ quá trình vẫn được compose trong một pipeline.

### 4.3. Không validate trong một subscription riêng

Không làm như sau:

```java
request.bodyToMono(CreateProductRequest.class)
        .subscribe(this::validate);

return ServerResponse.ok().build();
```

Đây là **anti-pattern**. Subscription đầu đọc body và chạy validation độc lập; handler lại trả response ngay. Kết quả validation không còn quyết định response, lỗi không nằm trong cùng pipeline và cancellation của request không quản lý đúng nhánh đó.

Hãy nối bước decode, validate, service và response bằng `flatMap`/`map` rồi return publisher cuối cùng.

## 5. Tạo error response rõ ràng

Một API lỗi có thể dùng cấu trúc như:

```json
{
  "code": "VALIDATION_FAILED",
  "violations": [
    {
      "field": "name",
      "message": "name is required"
    },
    {
      "field": "price",
      "message": "price must be greater than zero"
    }
  ]
}
```

Ví dụ DTO:

```java
public record FieldViolation(String field, String message) {}

public record ApiValidationError(
        String code,
        List<FieldViolation> violations) {}
```

Hàm chuyển đổi:

```java
private ApiValidationError toApiError(Errors errors) {
    List<FieldViolation> violations = errors.getAllErrors().stream()
            .map(error -> new FieldViolation(
                    error instanceof FieldError fieldError
                            ? fieldError.getField()
                            : "$",
                    error.getDefaultMessage() == null
                            ? "invalid value"
                            : error.getDefaultMessage()))
            .sorted(Comparator.comparing(FieldViolation::field))
            .toList();

    return new ApiValidationError("VALIDATION_FAILED", violations);
}
```

Đây là **đoạn minh họa** cần import `FieldError`, `Errors`, `Comparator` và `List`. Sắp xếp theo field giúp output ổn định trong test và dễ so sánh. Global error được đưa vào field path `"$"` để client biết lỗi không gắn với một property riêng.

Hãy giữ thông điệp lỗi ngắn và không chứa rejected value nhạy cảm. Nếu client cần logic máy đọc được, có thể thêm error code riêng thay vì buộc client phân tích câu chữ.

## 6. Validation với Jakarta Bean Validation

Spring Validator là abstraction của Spring; Jakarta Bean Validation cung cấp chuẩn annotation như `@NotBlank`, `@NotNull`, `@Positive`, `@Email` và `@Size`.

Trong functional handler, bạn có thể inject một validator dùng chung dựa trên `LocalValidatorFactoryBean`. Với Spring Boot, thêm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Spring Boot cấu hình Bean Validation provider khi starter có mặt. `LocalValidatorFactoryBean` là cầu nối giữa Jakarta Validation và Spring validation API; nó triển khai các abstraction tương ứng để có thể dùng trong handler.

DTO:

```java
public class CreateProductRequest {
    @NotBlank(message = "name is required")
    @Size(max = 80, message = "name must be at most 80 characters")
    private String name;

    @NotNull(message = "price is required")
    @Positive(message = "price must be greater than zero")
    private BigDecimal price;

    @NotBlank(message = "sku is required")
    @Pattern(regexp = "[A-Z0-9-]{3,20}",
             message = "sku must contain 3 to 20 uppercase letters, digits or hyphens")
    private String sku;

    @NotNull(message = "address is required")
    @Valid
    private Address address;

    // getters and setters

    public static class Address {
        @NotBlank(message = "city is required")
        private String city;

        @NotBlank(message = "country is required")
        private String country;

        // getters and setters
    }
}
```

Khi gọi validator, `@Valid` trên property `address` yêu cầu cascade validation vào object con. Tuy nhiên, chính handler vẫn phải gọi `validator.validate(...)`. Annotation không tự kích hoạt validation chỉ vì DTO được decode.

### 6.1. Dùng SmartValidator trong handler

`org.springframework.validation.SmartValidator` mở rộng Spring Validator để hỗ trợ validation hints, thường được dùng làm validation groups:

```java
@Component
public class ProductHandler {
    private final SmartValidator validator;

    public ProductHandler(SmartValidator validator) {
        this.validator = validator;
    }

    private Errors validate(CreateProductRequest input) {
        Errors errors =
                new BeanPropertyBindingResult(input, "createProductRequest");

        validator.validate(input, errors);
        return errors;
    }
}
```

Đây là **đoạn minh họa**. Trong ứng dụng Spring Boot có Bean Validation provider, `LocalValidatorFactoryBean` mặc định có thể được inject qua interface `SmartValidator`. Nếu tự đăng ký nhiều validator, dùng qualifier hoặc cấu hình rõ bean cần tiêm.

### 6.2. Validation groups

Một DTO có thể dùng cho cả tạo mới và cập nhật. Group cho phép chọn quy tắc cần chạy theo thao tác:

```java
public interface Create {}
public interface Update {}

public class ProductInput {
    @NotBlank(groups = Create.class)
    private String name;

    @NotNull(groups = Create.class)
    @Positive(groups = {Create.class, Update.class})
    private BigDecimal price;

    // getters and setters
}
```

Trong handler tạo mới:

```java
Errors errors = new BeanPropertyBindingResult(input, "productInput");
validator.validate(input, errors, Default.class, Create.class);
```

`SmartValidator.validate(target, errors, hints...)` truyền group như validation hint tới Bean Validation provider. Nếu chỉ chọn `Create.class`, các constraint thuộc group `Default` không tự động chạy, trừ khi group được thiết kế kế thừa hoặc được đưa vào danh sách.

Nếu dùng Jakarta `Validator` trực tiếp, cách gọi tương ứng là:

```java
Set<ConstraintViolation<ProductInput>> violations =
        jakartaValidator.validate(input, Default.class, Create.class);
```

Trong functional endpoint, `@Validated(Create.class)` trên một method argument không tự làm handler chạy group như annotated controller. Hãy gọi đúng group tường minh qua `SmartValidator` hoặc Jakarta `Validator`.

### 6.3. Cascade validation cho object con và collection

`@Valid` trên field/record component có tác dụng khi validator được gọi:

```java
public class BatchCreateRequest {
    @NotEmpty
    private List<@Valid CreateProductRequest> products;

    // getter and setter
}
```

`@NotEmpty` yêu cầu list có phần tử; `@Valid` trên phần tử yêu cầu validate từng object. Với collection lớn, validation đồng bộ có chi phí CPU theo số phần tử; giới hạn kích thước request và số item trước khi xử lý để tránh tiêu thụ tài nguyên không kiểm soát.

## 7. Phân biệt body rỗng, JSON sai và validation fail

Ba tình huống này xảy ra ở các giai đoạn khác nhau:

| Đầu vào | Điều gì xảy ra? | Cách xử lý |
| --- | --- | --- |
| Không có body | `bodyToMono` có thể hoàn tất rỗng | Dùng `switchIfEmpty` để phát lỗi “body required” hoặc response 400. |
| JSON sai cú pháp/kiểu | Message reader/codec phát lỗi khi deserialize | Để WebFlux xử lý input/decoding error hoặc map riêng ở error layer. |
| JSON hợp lệ nhưng vi phạm constraint | Có object Java; validator ghi errors | Trả 400 với field violations. |

Ví dụ body bắt buộc:

```java
Mono<CreateProductRequest> body = request
        .bodyToMono(CreateProductRequest.class)
        .switchIfEmpty(Mono.error(
                new ServerWebInputException("Request body is required")));
```

Đây là **đoạn minh họa**. `switchIfEmpty` chỉ xử lý body publisher rỗng. Nó không bắt lỗi decode vì lỗi vẫn là error signal, không phải empty completion.

Nếu cần một error contract đồng nhất, có thể xử lý `ServerWebInputException`/codec exception tại lớp xử lý lỗi WebFlux. Đừng biến mọi lỗi decode thành field violation giả vì lúc đó chưa có object để validate.

### 7.1. Request content type và codec

`request.bodyToMono(CreateProductRequest.class)` cần một reader có thể đọc Content-Type được gửi. Với JSON, client nên gửi `Content-Type: application/json`. Nếu media type không được hỗ trợ hoặc body không thể chuyển đổi, handler sẽ nhận error signal từ quá trình đọc body.

Đối với endpoint function, router có thể kiểm tra predicate như `contentType(APPLICATION_JSON)` trước khi gọi handler. Predicate này kiểm tra media type; nó không kiểm tra field constraint và không thay thế validator.

## 8. Chương trình Spring Boot 3.3.5 chạy được

Ví dụ hoàn chỉnh dưới đây dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5**, WebFlux functional endpoints và Jakarta Bean Validation qua `SmartValidator`. Handler tự kiểm tra DTO rồi tạo response 400 có cấu trúc.

Cấu trúc:

```text
functional-validation-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── ValidationApplication.java
    │   ├── CreateProductRequest.java
    │   ├── ProductHandler.java
    │   ├── ProductRoutes.java
    │   └── ProductService.java
    └── test/java/demo/
        └── ProductRoutesTest.java
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
    <artifactId>functional-validation-demo</artifactId>
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

### 8.3. CreateProductRequest.java

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public class CreateProductRequest {
    @NotBlank(message = "name is required")
    @Size(max = 80, message = "name must be at most 80 characters")
    private String name;

    @NotNull(message = "price is required")
    @Positive(message = "price must be greater than zero")
    private BigDecimal price;

    @NotBlank(message = "sku is required")
    @Pattern(regexp = "[A-Z0-9-]{3,20}",
             message = "sku must contain 3 to 20 uppercase letters, digits or hyphens")
    private String sku;

    @NotNull(message = "address is required")
    @Valid
    private Address address;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public Address getAddress() { return address; }
    public void setAddress(Address address) { this.address = address; }

    public static class Address {
        @NotBlank(message = "city is required")
        private String city;

        @NotBlank(message = "country is required")
        private String country;

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }

        public String getCountry() { return country; }
        public void setCountry(String country) { this.country = country; }
    }
}
```

### 8.4. ProductService.java

```java
package demo;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProductService {
    private final AtomicLong ids = new AtomicLong();

    public record Product(
            long id,
            String name,
            String sku,
            String price) {}

    public Mono<Product> create(CreateProductRequest request) {
        return Mono.fromSupplier(() ->
                new Product(
                        ids.incrementAndGet(),
                        request.getName(),
                        request.getSku(),
                        request.getPrice().toPlainString()));
    }
}
```

Service chỉ minh họa lưu thành công trong bộ nhớ. Trong ứng dụng thực tế, thay bằng repository reactive và xử lý lỗi persistence riêng.

### 8.5. ProductHandler.java

```java
package demo;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.SmartValidator;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class ProductHandler {
    private final SmartValidator validator;
    private final ProductService service;

    public ProductHandler(SmartValidator validator, ProductService service) {
        this.validator = validator;
        this.service = service;
    }

    public record FieldViolation(String field, String message) {}
    public record ApiError(String code, List<FieldViolation> violations) {}

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateProductRequest.class)
                .switchIfEmpty(Mono.error(
                        new org.springframework.web.server.ServerWebInputException(
                                "Request body is required")))
                .flatMap(input -> {
                    Errors errors = new BeanPropertyBindingResult(
                            input, "createProductRequest");

                    validator.validate(input, errors);

                    if (errors.hasErrors()) {
                        return ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(toApiError(errors));
                    }

                    return service.create(input)
                            .flatMap(product ->
                                    ServerResponse.created(
                                                    URI.create("/products/" + product.id()))
                                            .contentType(MediaType.APPLICATION_JSON)
                                            .bodyValue(product));
                });
    }

    private ApiError toApiError(Errors errors) {
        List<FieldViolation> violations = errors.getAllErrors().stream()
                .map(this::toViolation)
                .sorted(Comparator.comparing(FieldViolation::field))
                .toList();

        return new ApiError("VALIDATION_FAILED", violations);
    }

    private FieldViolation toViolation(ObjectError error) {
        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "$";

        String message = error.getDefaultMessage() == null
                ? "invalid value"
                : error.getDefaultMessage();

        return new FieldViolation(field, message);
    }
}
```

### 8.6. ProductRoutes.java

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class ProductRoutes {
    @Bean
    RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
        return RouterFunctions.route()
                .POST("/products", handler::create)
                .build();
    }
}
```

### 8.7. Chạy ứng dụng

Tại thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Gửi request hợp lệ:

```bash
curl -i -X POST http://localhost:8080/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Keyboard","price":49.90,"sku":"KEY-100","address":{"city":"Hanoi","country":"VN"}}'
```

Kết quả là HTTP **201 Created**, có header `Location: /products/1` ở lần tạo đầu tiên và body:

```json
{
  "id": 1,
  "name": "Keyboard",
  "sku": "KEY-100",
  "price": "49.90"
}
```

Gửi request vi phạm nhiều constraint:

```bash
curl -i -X POST http://localhost:8080/products \
  -H "Content-Type: application/json" \
  -d '{"name":" ","price":-5,"sku":"bad sku","address":{"city":"","country":"VN"}}'
```

Kết quả là HTTP **400 Bad Request**, body có dạng:

```json
{
  "code": "VALIDATION_FAILED",
  "violations": [
    {"field":"address.city","message":"city is required"},
    {"field":"name","message":"name is required"},
    {"field":"price","message":"price must be greater than zero"},
    {"field":"sku","message":"sku must contain 3 to 20 uppercase letters, digits or hyphens"}
  ]
}
```

Danh sách được sắp xếp theo field để kết quả ổn định. Các violation thực tế được tạo từ validator; nếu thêm constraint, response sẽ có thêm lỗi tương ứng.

### 8.8. ProductRoutesTest.java

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
class ProductRoutesTest {
    @Autowired
    WebTestClient client;

    @Test
    void validRequestCreatesProduct() {
        client.post()
                .uri("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Keyboard",
                          "price": 49.90,
                          "sku": "KEY-100",
                          "address": {
                            "city": "Hanoi",
                            "country": "VN"
                          }
                        }
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().valueEquals("Location", "/products/1")
                .expectBody()
                .jsonPath("$.name").isEqualTo("Keyboard")
                .jsonPath("$.sku").isEqualTo("KEY-100");
    }

    @Test
    void invalidRequestReturnsFieldViolations() {
        client.post()
                .uri("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": " ",
                          "price": -5,
                          "sku": "bad sku",
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

    @Test
    void missingBodyReturnsBadRequest() {
        client.post()
                .uri("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

Chạy:

```bash
mvn test
```

Test xác nhận request hợp lệ tạo sản phẩm, request có constraint violations trả 400 với body lỗi, và body rỗng bị từ chối. Test integration này kiểm tra contract HTTP thực tế của RouterFunction/HandlerFunction và validator được Spring inject.

## 9. Dùng Spring Validator tự viết thay cho annotation constraint

Không phải dự án nào cũng cần Jakarta Bean Validation. Khi quy tắc đơn giản, hoặc cần tương thích với hệ thống validation hiện có của Spring, có thể tạo custom `Validator`:

```java
@Component
public class ProductInputValidator implements Validator {
    @Override
    public boolean supports(Class<?> type) {
        return ProductInput.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ProductInput input = (ProductInput) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "name", "name.required", "name is required");

        if (input.getQuantity() == null) {
            errors.rejectValue(
                    "quantity", "quantity.required", "quantity is required");
        } else if (input.getQuantity() <= 0) {
            errors.rejectValue(
                    "quantity", "quantity.positive",
                    "quantity must be greater than zero");
        }
    }
}
```

Đây là **đoạn minh họa độc lập**, giả sử `ProductInput` có các JavaBean getter/setter. Handler dùng nó giống như validator ở ví dụ chính. Nếu có nhiều validator cho cùng DTO, có thể gọi tuần tự hoặc phối hợp bằng `SmartValidator`/cấu hình riêng; tránh tạo validator mới ở mỗi request nếu nó có dependency hoặc state dùng chung.

### 9.1. Khi nào dùng Jakarta Validator trực tiếp?

Nếu cần lấy tập `ConstraintViolation<T>` thay vì Spring `Errors`:

```java
Set<ConstraintViolation<CreateProductRequest>> violations =
        jakartaValidator.validate(input);

if (!violations.isEmpty()) {
    // Chuyển violation.getPropertyPath() và getMessage()
    // thành API error response.
}
```

`jakarta.validation.Validator` thích hợp khi logic cần dùng trực tiếp API chuẩn Jakarta, hoặc muốn chia sẻ cùng validator với một thành phần Java khác. `LocalValidatorFactoryBean` cho phép tích hợp với Spring. Nếu handler cần `Errors` và validation hints, `SmartValidator` thuận tiện hơn.

## 10. Quy tắc bất đồng bộ phải nằm trong reactive service

Bean Validation và Spring `Validator` đều là API gọi đồng bộ. Một validator không trả `Mono<Boolean>`; nó chạy trong thread đang gọi `validate`.

Ví dụ không nên làm:

```java
@Override
public void validate(Object target, Errors errors) {
    ProductInput input = (ProductInput) target;
    boolean exists = repository.existsBySku(input.getSku()).block();
    if (exists) {
        errors.rejectValue("sku", "sku.exists", "sku already exists");
    }
}
```

Đây là **anti-pattern**. Truy vấn có thể block event-loop, làm giảm throughput và gây lỗi khi block trên thread không cho phép blocking. Nó cũng trộn validation đồng bộ với I/O bất đồng bộ.

Hãy tách thành hai giai đoạn:

1. Validator kiểm tra hình thức và cấu trúc: SKU có đúng định dạng, tên có giá trị, quantity dương.
2. Service kiểm tra trạng thái bên ngoài: SKU đã tồn tại chưa, người dùng có quyền tạo sản phẩm không, hạn mức còn đủ không.

Ví dụ:

```java
return request.bodyToMono(CreateProductRequest.class)
        .flatMap(input -> {
            Errors errors = validate(input);
            if (errors.hasErrors()) {
                return badRequestResponse(errors);
            }

            return productRepository.existsBySku(input.getSku())
                    .flatMap(exists -> {
                        if (exists) {
                            return conflictResponse("SKU_ALREADY_EXISTS");
                        }
                        return productService.create(input)
                                .flatMap(this::createdResponse);
                    });
        });
```

Đây là **đoạn minh họa**, repository và helper phải trả publisher reactive. Dùng `flatMap` để chờ kết quả bất đồng bộ và quyết định response. Nếu hai request đồng thời cùng kiểm tra SKU chưa tồn tại, cả hai vẫn có thể vượt qua bước kiểm tra trước khi ghi; database cần unique constraint và service phải xử lý duplicate-key race condition.

## 11. Những điểm cần chú ý trong functional handler

### 11.1. Body chỉ nên được đọc một lần

`request.bodyToMono(CreateProductRequest.class)` tiêu thụ request body theo pipeline. Không tạo một subscription riêng để log body rồi tiếp tục decode lần nữa. Nếu cần log dữ liệu, ưu tiên metadata không nhạy cảm hoặc thiết kế một bước đọc/ghi lại body có giới hạn và quản lý buffer rõ ràng.

### 11.2. Validation lỗi phải ngăn side effect

Thứ tự đúng là decode → validate → service. Không ghi database, gửi message hay gọi API ngoài trước khi biết object hợp lệ. Nếu validation fail, service không được chạy.

### 11.3. Kiểm tra toàn bộ object khi cần

`validator.validate(input, errors)` mặc định kiểm tra group `Default`. Với DTO lồng nhau, đặt `@Valid` ở property cần cascade. Với class-level constraint, validator có thể thêm global error. Với collection, kiểm tra kích thước và cascade từng phần tử.

### 11.4. Validation không thay thế authorization

Một request có thể hợp lệ về kiểu dữ liệu nhưng người gửi không có quyền thực hiện hành động. Kiểm tra quyền phải dựa trên principal đã xác thực và policy server-side. Không xem trường `ownerId`, `role` hoặc `tenantId` trong JSON là bằng chứng người dùng có quyền sở hữu.

### 11.5. Giới hạn kích thước request và collection

Validation diễn ra sau khi codec đã deserialize object. Với body rất lớn, ứng dụng đã phải tiêu thụ tài nguyên trước khi validator chạy. Cần cấu hình giới hạn memory/body size ở server/codec, giới hạn số phần tử và dùng streaming khi dữ liệu thực sự lớn.

### 11.6. Message lỗi và localization

Spring Validator và Bean Validation có thể dùng message code/MessageSource. Trong API công khai, chọn message nhất quán, có thể dịch theo locale và không tiết lộ cấu trúc nội bộ. Nếu client cần logic máy đọc được, trả error code ổn định cùng field path; đừng bắt client so sánh câu chữ đã dịch.

## 12. Lỗi thường gặp và cách xử lý

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `@Valid` tự chạy trong WebFlux.fn | DTO có annotation nhưng không được validate | Inject validator và gọi tường minh trong handler. |
| Chỉ gọi `bodyToMono` rồi lưu dữ liệu | Decode thành công nhưng constraint chưa được kiểm tra | Thêm validation trước service/persistence. |
| Gọi `validator.validate` trước khi body được decode | Chưa có object để kiểm tra | Đặt validator trong `flatMap`/`doOnNext` sau body extraction. |
| Dùng `request.bind` để đọc JSON body | Nhầm binding path/query/header với body codec | Dùng `bodyToMono`/`bodyToFlux` cho body. |
| Dùng `Errors` nhưng chỉ đọc `getFieldErrors()` | Bỏ sót lỗi cấp object | Đọc `getAllErrors()` khi cần đầy đủ. |
| Tự trả 200 dù errors tồn tại | Client hiểu request được chấp nhận | Trả `ServerResponse.badRequest()` hoặc ném `ServerWebInputException`. |
| Đưa rejected value/stack trace vào response | Có thể lộ dữ liệu nhạy cảm | Chỉ trả field path và message công khai. |
| Nghĩ JSON sai kiểu là validation violation | Chưa có DTO để validate | Xử lý lỗi decode riêng với Bean Validation. |
| Bỏ qua body rỗng | Handler có thể hoàn tất rỗng và không tạo response mong muốn | Dùng `switchIfEmpty` và quy định body bắt buộc. |
| Gọi `subscribe()` bên trong handler | Tách side effect khỏi HTTP lifecycle | Compose bằng `flatMap` và return publisher. |
| Gọi `block()` trong validator | Chặn event-loop | Chỉ validate đồng bộ; I/O chuyển sang service reactive. |
| Truy vấn database trong ConstraintValidator | Validator đồng bộ chặn I/O | Kiểm tra dữ liệu bên ngoài trong service bằng publisher. |
| Dùng `@Validated` rồi nghĩ group tự được chọn trong handler | Không có cơ chế tự động gọi validator như annotated argument | Gọi `SmartValidator.validate(..., group)` hoặc Jakarta `Validator.validate(..., group)`. |
| Quên cascade ở object con | Constraint lồng nhau không chạy | Đặt `@Valid` trên property/collection element. |
| Không giới hạn body/list lớn | Validation có thể tiêu thụ CPU/memory đáng kể | Đặt giới hạn request và số phần tử trước khi xử lý. |
| Chỉ kiểm tra tồn tại rồi ghi dữ liệu | Race condition giữa hai request đồng thời | Dùng unique constraint và xử lý conflict ở persistence layer. |
| Dùng validation thay authorization | Người dùng có thể gửi dữ liệu hợp lệ nhưng không có quyền | Xác thực và kiểm tra quyền bằng Spring Security/policy. |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao WebFlux functional handler cần gọi validator tường minh?  
**Đáp án:** Handler nhận `ServerRequest` và tự đọc body; không có annotated method argument resolver tự kích hoạt validation cho DTO. Sau khi decode, handler phải gọi `Validator.validate` hoặc Jakarta `Validator.validate`.

**Câu 2.** `request.bodyToMono(CreateProductRequest.class)` đã kiểm tra `@NotBlank` chưa?  
**Đáp án:** Chưa. Nó đọc và deserialize body. Phải gọi validator sau khi có object.

**Câu 3.** Vai trò của `BeanPropertyBindingResult` là gì?  
**Đáp án:** Nó tạo vùng chứa `Errors` gắn với object, lưu field error và global error để handler quyết định response.

**Câu 4.** `ServerWebInputException` thường được dùng để làm gì trong functional endpoint?  
**Đáp án:** Ném lỗi đầu vào khi validation fail; WebFlux xử lý exception này thành HTTP 400 theo cơ chế mặc định.

**Câu 5.** Tại sao không nên gọi database trong `Validator.validate`?  
**Đáp án:** Spring Validator/Jakarta Bean Validation là API đồng bộ. Query blocking có thể chặn event-loop. Kiểm tra phụ thuộc I/O nên nằm trong service reactive.

**Câu 6.** `@Valid` trên nested address có tác dụng gì?  
**Đáp án:** Khi validator thực sự được gọi, nó cascade sang object address và kiểm tra các constraint bên trong.

**Câu 7.** Làm thế nào để chọn group Create trong handler?  
**Đáp án:** Dùng `SmartValidator.validate(input, errors, Default.class, Create.class)` hoặc Jakarta `Validator.validate(input, Default.class, Create.class)`. `@Validated` không tự kích hoạt validation trong WebFlux.fn.

**Câu 8.** JSON có `"price": "many"` trong khi DTO mong đợi `BigDecimal` là lỗi gì?  
**Đáp án:** Lỗi deserialize/codec xảy ra trước validation. Chưa có object hợp lệ để kiểm tra constraint giá dương.

**Câu 9.** Nếu validation fail, service có được gọi không?  
**Đáp án:** Không. Handler phải kiểm tra errors trước khi compose service create/save.

**Câu 10.** Hai request cùng vượt qua kiểm tra “SKU chưa tồn tại” rồi ghi đồng thời có thể gây gì?  
**Đáp án:** Race condition. Cần unique constraint ở database và xử lý duplicate-key error; validation ở tầng ứng dụng không đảm bảo tính duy nhất khi có concurrency.

## Ghi nhớ

- Trong WebFlux.fn, `HandlerFunction` nhận `ServerRequest` và trả `Mono<ServerResponse>`. Handler đọc body bằng `bodyToMono`/`bodyToFlux` rồi **tự gọi validator**.
- `Spring Validator` dùng `Errors` và `BeanPropertyBindingResult`; `SmartValidator` bổ sung validation hints/groups. Jakarta Bean Validation có thể được tích hợp qua `LocalValidatorFactoryBean`.
- `@Valid` trên nested DTO giúp cascade khi validator được gọi; `@Validated` không tự kích hoạt validation trong functional handler.
- Decode lỗi, body rỗng và constraint violation là ba tình huống khác nhau. Chọn cách xử lý và response 4xx rõ ràng.
- Validation đồng bộ chỉ kiểm tra cấu trúc/quy tắc nhẹ. Kiểm tra cần database/network phải compose bằng `Mono`/`Flux` trong service.
- Luôn validate trước side effect, trả error contract an toàn, giới hạn body và collection, không `block()` hay tự `subscribe()`.

### Tài liệu tham khảo

1. [Spring Framework – WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): `HandlerFunction`, `ServerRequest.bodyToMono` và ví dụ validation bằng Spring `Validator`.
2. [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Spring Validator, Jakarta Bean Validation, `LocalValidatorFactoryBean` và validation groups.
3. [Spring Boot – Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): cấu hình provider qua `spring-boot-starter-validation`.
4. [Spring Framework – WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html): `ServerWebInputException` và xử lý lỗi HTTP.
5. [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraint annotations, cascade validation, groups và `ConstraintValidator`.
6. [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử HTTP endpoint reactive.

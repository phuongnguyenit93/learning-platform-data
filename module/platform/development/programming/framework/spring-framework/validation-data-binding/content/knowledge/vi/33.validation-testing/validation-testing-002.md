# Kiểm thử lỗi một trường, toàn đối tượng và đường dẫn lồng trong Spring Framework

## Mục tiêu học tập

Spring MVC và Spring Validation có thể phát hiện nhiều kiểu lỗi trên cùng một request: một field thiếu dữ liệu, mối quan hệ giữa hai field không hợp lệ, hoặc một trường nằm sâu trong đối tượng lồng/list không đáp ứng constraint. Nếu chỉ viết một test kiểu `status().isBadRequest()`, ta chưa biết **rule nào thực sự chạy**, lỗi được ghi vào **đúng cấp** hay không và client có nhận **đường dẫn chính xác** để đánh dấu ô nhập hay không.

Bài thuộc nhóm **Kiểm thử** của module Spring Framework — validation-data-binding, tập trung vào ba trường hợp:

1. **Lỗi một trường:** ví dụ `customerName=""` vi phạm `@NotBlank`, được Spring thể hiện bằng `FieldError` cho `customerName`.
2. **Lỗi toàn đối tượng:** ví dụ `endDate` sớm hơn `startDate`, vi phạm quy tắc quan hệ hai thuộc tính, được thể hiện bằng `ObjectError` trong `getGlobalErrors()`.
3. **Lỗi đường dẫn lồng:** ví dụ `shippingAddress.city=""` hoặc `lines[0].sku=""`, vẫn là `FieldError` nhưng có đường dẫn `shippingAddress.city` và `lines[0].sku`.

Sau khi học, bạn sẽ:

- Phân biệt `Errors`, `BindingResult`, `FieldError`, `ObjectError` và `ConstraintViolation`.
- Hiểu vai trò của `@Valid` khi cascade vào object, collection và container elements.
- Viết custom Jakarta class-level constraint tạo **global error**, thay vì luôn đẩy lỗi vào một field.
- Dùng `getFieldErrors()`, `getGlobalErrors()`, `getAllErrors()`, `hasFieldErrors(...)`, `getFieldError(...)` và `getErrorCount()`.
- Kiểm thử validation thuần bằng `jakarta.validation.Validator`, kiểm thử Spring `Errors` bằng `MapBindingResult` và kiểm thử HTTP bằng `MockMvc`.
- Nhận diện `MethodArgumentNotValidException` cho `@Valid @RequestBody` khác với `HttpMessageNotReadableException` do JSON hỏng, và `HandlerMethodValidationException` của method validation (Spring 6.1+).
- Viết ứng dụng Spring Boot 3.5 / Java 17+ có JSON DTO lồng, danh sách phần tử, kiểm thử riêng ba cấp lỗi và trường hợp hỗn hợp.
- Tránh các test dễ vỡ do thứ tự constraint violations, nội dung message thay đổi theo locale hoặc đường dẫn chưa được chuẩn hóa.

## 1. Ba cấp lỗi không phải ba loại HTTP status

Xét một request tạo đơn đặt hàng:

~~~json
{
  "customerName": "Lan",
  "shippingAddress": {
    "street": "12 Main St",
    "city": "Ha Noi",
    "postalCode": "12345"
  },
  "lines": [
    {"sku": "BOOK-1", "quantity": 2}
  ],
  "startDate": "2026-11-01",
  "endDate": "2026-11-03"
}
~~~

Các quy tắc ví dụ:

- `customerName` bắt buộc có chữ: `@NotBlank`.
- `shippingAddress.city` bắt buộc có chữ: `@NotBlank` ở nested record, kèm `@Valid` ở cạnh từ request sang address.
- `lines[0].sku` bắt buộc có chữ, `lines[0].quantity` phải ít nhất 1: nested list + `@Valid`.
- `endDate` không được trước `startDate`: class-level constraint `@ValidPeriod` trên toàn request.

Khi thay giá trị:

| Request thay đổi | Kiểu rule | Spring error | Đường dẫn / đối tượng |
| --- | --- | --- | --- |
| `customerName=""` | Property constraint | `FieldError` | `customerName` |
| `endDate="2026-10-31"` | Class-level constraint | `ObjectError` (global) | `createOrderRequest` |
| `shippingAddress.city=""` | Nested bean constraint | `FieldError` | `shippingAddress.city` |
| `lines[0].sku=""` | Nested list element | `FieldError` | `lines[0].sku` |
| `lines[0].quantity=0` | Nested numeric constraint | `FieldError` | `lines[0].quantity` |
| JSON thiếu dấu đóng ngoặc | JSON parse/deserialize | Không nhất thiết có `BindingResult` | `HttpMessageNotReadableException` |

**Tất cả lỗi validation đầu vào này thường có thể dẫn đến HTTP 400**, nhưng điều quan trọng của bài là cấu trúc lỗi ở phía Spring. HTTP 400 một mình không chứng minh lỗi toàn đối tượng hay path lồng đã được xử lý.

### Sơ đồ đường đi

~~~text
HTTP JSON / form
        |
        v
Deserialize / Bind
        |
        +-- Hỏng cú pháp JSON → HttpMessageNotReadableException
        +-- Form property convert fail → typeMismatch FieldError
        |
        v
@Valid / @Validated
        |
        +-- @NotBlank(customerName)
        |         → FieldError("customerName")
        |
        +-- @ValidPeriod(CreateOrderRequest)
        |         → ObjectError("createOrderRequest")
        |
        +-- @Valid shippingAddress
        |         → FieldError("shippingAddress.city")
        |
        '-- @Valid lines element [0]
                  → FieldError("lines[0].sku")
        |
        v
BindingResult
        |
        +-- getFieldErrors()
        +-- getGlobalErrors()
        '-- getAllErrors()
~~~

`@Valid` trên một nested property **không phải constraint thay thế `@NotNull`**. Nó yêu cầu provider đi sâu vào object khi object có mặt; nếu nested object là null, cascade thường không kiểm tra thuộc tính con. Khi bắt buộc có address, thêm `@NotNull` riêng trên property đó.

## 2. FieldError và ObjectError khác nhau thế nào?

### 2.1. ObjectError

`org.springframework.validation.ObjectError` mô tả lỗi gắn với toàn target object hoặc một object được bind, không trỏ đến một property cụ thể. Những accessor đáng chú ý:

~~~java
String objectName = error.getObjectName();
String code = error.getCode();
String defaultMessage = error.getDefaultMessage();
String[] codes = error.getCodes();
Object[] arguments = error.getArguments();
~~~

Đây là snippet giả định `error` có kiểu `ObjectError`. `objectName` thường là tên của binding target do Spring đặt, ví dụ `createOrderRequest`. `getCode()` là mã lỗi cơ sở như `ValidPeriod`; `getCodes()` có thể chứa các mã chi tiết hơn dùng cho MessageSource.

### 2.2. FieldError mở rộng ObjectError

`org.springframework.validation.FieldError` là subclass của `ObjectError`. Nó có thông tin bổ sung:

~~~java
String field = fieldError.getField();
Object rejected = fieldError.getRejectedValue();
boolean bindingFailure = fieldError.isBindingFailure();
~~~

Lỗi `@NotBlank` sau binding thành công thường có `isBindingFailure() == false`. Trái lại, khi form gửi `quantity=abc` nhưng Java cần `Integer`, Spring binder không chuyển kiểu được và có thể tạo FieldError với `typeMismatch`, `isBindingFailure() == true`.

**Không log hay trả toàn bộ `rejectedValue` cho client**: trường đó có thể chứa mật khẩu, token, hoặc dữ liệu cá nhân. Trong test, chỉ đọc rejected value đối với dữ liệu giả không nhạy cảm.

### 2.3. BindingResult là một tập hợp, không chỉ một lỗi

`BindingResult` mở rộng `Errors`:

~~~java
int total = errors.getErrorCount();
int fieldCount = errors.getFieldErrorCount();
int globalCount = errors.getGlobalErrorCount();

boolean hasAny = errors.hasErrors();
boolean hasName = errors.hasFieldErrors("customerName");
boolean hasGlobal = errors.hasGlobalErrors();

List<FieldError> fieldErrors = errors.getFieldErrors();
List<ObjectError> globalErrors = errors.getGlobalErrors();
List<ObjectError> allErrors = errors.getAllErrors();
~~~

Snippet giả định `errors` có kiểu `BindingResult`. `getAllErrors()` gồm **field + global**. Vì `FieldError extends ObjectError`, kiểu trả về là `List<ObjectError>` nhưng **không** có nghĩa tất cả phần tử là global error.

Sai lầm phổ biến:

~~~java
for (ObjectError error : errors.getAllErrors()) {
    // Coi mọi lỗi là object-level và bỏ qua field path!
}
~~~

Nếu muốn tách đúng, dùng `getFieldErrors()` và `getGlobalErrors()` hoặc kiểm tra `instanceof FieldError` có chủ đích.

### 2.4. Một đường dẫn lồng vẫn là FieldError

Khi `shippingAddress.city` sai, Spring không tạo một loại `NestedError` riêng. Đường dẫn lồng thường được biểu diễn trong `FieldError.getField()`:

~~~text
customerName
shippingAddress.city
lines[0].sku
lines[1].quantity
~~~

`getFieldErrors("shippingAddress.city")` chọn lỗi của field đó. Nếu cần đối sánh trong tests, dùng **đường dẫn thực tế của model** thay vì rút gọn mọi nested error về `city`. Nếu framework/adapter khác nhau trong cách biểu diễn container element, hãy quan sát actual paths trước khi khóa contract; ví dụ chạy được bên dưới dùng Spring MVC/Jakarta Validator trên Boot 3.5.

## 3. Jakarta Bean Validation và đường dẫn ConstraintViolation

Trước khi vào Spring MVC, Jakarta Validation cho phép validate Java object trực tiếp:

~~~java
Set<ConstraintViolation<CreateOrderRequest>> violations =
        validator.validate(request);
~~~

`jakarta.validation.Validator.validate(...)` trả một `Set`; nó **không tự ném `MethodArgumentNotValidException`**. Mỗi violation cung cấp:

~~~java
String message = violation.getMessage();
String path = violation.getPropertyPath().toString();
Object invalid = violation.getInvalidValue();
Class<?> annotationType = violation
        .getConstraintDescriptor()
        .getAnnotation()
        .annotationType();
~~~

Mã trên là snippet; `getInvalidValue()` chỉ nên dùng nội bộ có kiểm soát, không trả nguyên cho frontend.

Thông thường:

- Field-level `@NotBlank` trên `customerName` tạo path `customerName`.
- Class-level `@ValidPeriod` gắn trên root bean tạo path **rỗng** `""` theo default violation.
- Constraint trên nested bean tạo path như `shippingAddress.city`.
- Constraint trên phần tử list có thể tạo path như `lines[0].sku`, có metadata node cho container/index theo provider.

Spring dùng adapter (như `LocalValidatorFactoryBean` / Spring Validator adapter) để chuyển các `ConstraintViolation` thành `FieldError` hoặc `ObjectError` trong `BindingResult`. **Không** so trực tiếp số lượng `ConstraintViolation` với số lượng `FieldError` nếu còn có binding failures, các Spring Validators bổ sung, hoặc validation groups khác.

### Thứ tự violations không cố định

Jakarta Bean Validation trả `Set` nên không nên test:

~~~java
assertEquals("customerName",
        violations.iterator().next().getPropertyPath().toString());
~~~

Dùng `anyMatch`, `contains` trên tập path, hoặc sort trước khi so sánh. Tương tự, nếu JSON error response có mảng lỗi, API nên tự sort nếu contract cần thứ tự ổn định; nếu không, test không nên phụ thuộc vào vị trí mảng.

## 4. Tạo lỗi toàn đối tượng bằng class-level constraint

Quy tắc “`endDate` không được sớm hơn `startDate`” liên quan **hai thuộc tính**. Đặt `@PastOrPresent` hoặc `@Future` riêng từng property sẽ không mô tả được quan hệ này.

Ví dụ annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidPeriodValidator.class)
@Documented
public @interface ValidPeriod {
    String message() default "End date must not be before start date";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Kèm validator:

~~~java
public final class ValidPeriodValidator
        implements ConstraintValidator<ValidPeriod, CreateOrderRequest> {

    @Override
    public boolean isValid(CreateOrderRequest value,
                           ConstraintValidatorContext context) {
        if (value == null
                || value.startDate() == null
                || value.endDate() == null) {
            return true;
        }
        return !value.endDate().isBefore(value.startDate());
    }
}
~~~

Đây là các snippet; file đầy đủ có imports ở mục 7. Lưu ý:

1. `@Target(TYPE)` gắn constraint ở **class/record**, không vào một field.
2. Khi `isValid` trả false và không tự thay violation builder, Jakarta tạo violation tại root object. Spring chuyển nó thành **global ObjectError**.
3. Nếu một hoặc cả hai ngày null, class-level validator trả true và để `@NotNull` của từng field báo lỗi. Cách này tránh NPE và tránh hai thông báo trùng ý nghĩa.
4. Nếu muốn hiển thị lỗi quan hệ trên riêng `endDate`, có thể dùng `ConstraintValidatorContext.disableDefaultConstraintViolation()` rồi `buildConstraintViolationWithTemplate(...).addPropertyNode("endDate").addConstraintViolation()`. Khi đó lỗi thành **FieldError**, không còn là global error. Đó là quyết định thiết kế UI, không phải yêu cầu bắt buộc.

Tại sao cần test global errors riêng? Nếu người viết custom constraint vô tình gọi `addPropertyNode("endDate")`, rule vẫn thất bại và HTTP vẫn 400, nhưng `getGlobalErrors()` không còn chứa lỗi này. Chỉ test status không bắt được thay đổi contract.

## 5. Lỗi đường dẫn lồng: @Valid và collection

### 5.1. Nested bean

~~~java
public record ShippingAddress(
        @NotBlank String street,
        @NotBlank String city,
        @NotBlank String postalCode) {
}
~~~

Khi root DTO có:

~~~java
@NotNull @Valid ShippingAddress shippingAddress
~~~

thì `shippingAddress.city=""` sinh lỗi ở path `shippingAddress.city`. Nếu bỏ `@Valid`, constraint bên trong `ShippingAddress` **không tự được kiểm tra** qua việc validate root, dù root có `@NotNull`.

### 5.2. Nested collection

~~~java
public record OrderLine(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity) {
}
~~~

Khi root DTO có:

~~~java
@NotEmpty
List<@Valid OrderLine> lines
~~~

vi phạm `sku` của phần tử đầu có thể xuất hiện dưới path `lines[0].sku`. Vi phạm của phần tử thứ hai là `lines[1].sku`. Chú ý:

- Chỉ `@NotEmpty` trên List kiểm tra collection có ít nhất một phần tử; nó **không** cascade vào từng element.
- `@Valid` trên element/collection mới tạo cascade.
- Một `null` element không được cascade; nếu không cho phép null element, dùng type-use constraint như `List<@NotNull @Valid OrderLine>`.
- Với Map, path có thể biểu diễn key dạng `entries[sku-1].amount`; cần quan sát path thực tế của provider.
- Không dựng đường dẫn theo tên JSON hiển thị nếu model dùng `@JsonProperty` rename; path của Jakarta/Spring thường căn theo tên property Java, trừ khi có `PropertyNodeNameProvider` hoặc custom mapping.

### 5.3. Null object khác blank nested field

Hai case không giống nhau:

~~~json
{"shippingAddress": null}
~~~

và:

~~~json
{"shippingAddress": {"street":"12 Main","city":"","postalCode":"12345"}}
~~~

Trường hợp đầu tạo field error `shippingAddress` do `@NotNull`, không nhất thiết có `shippingAddress.city`. Trường hợp sau `@NotNull` đạt và `@Valid` đi sâu, tạo field error `shippingAddress.city` do `@NotBlank`.

### 5.4. Nested path với Spring Validator

Ngoài Jakarta, Spring thuần cho phép `Errors.pushNestedPath("shippingAddress")`, rồi `rejectValue("city",...)`:

~~~java
errors.pushNestedPath("shippingAddress");
try {
    errors.rejectValue("city", "city.required");
} finally {
    errors.popNestedPath();
}
~~~

Đường dẫn field được ghi thành `shippingAddress.city`. `pushNestedPath` và `popNestedPath` nên cân bằng kể cả khi validator phát exception. Nếu không pop, những field errors tạo sau đó có thể bị gắn sai prefix.

## 6. Khi nào xuất hiện MethodArgumentNotValidException?

Trên Spring MVC 6.2, với controller:

~~~java
@PostMapping("/api/orders")
ResponseEntity<?> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

và không có `Errors`/`BindingResult` ngay sau argument, khi **Bean Validation của object** thất bại, Spring thường ném `org.springframework.web.bind.MethodArgumentNotValidException`. Exception này cung cấp `BindingResult` qua `getBindingResult()`.

Nếu muốn controller tự xử lý lỗi (ví dụ HTML form), có thể nhận `BindingResult` ngay sau `@ModelAttribute`:

~~~java
@PostMapping("/form")
String submit(
        @Valid @ModelAttribute("createOrderRequest")
        CreateOrderRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "order-form";
    }
    return "redirect:/success";
}
~~~

Đây là snippet form-flow, không nằm trong demo JSON runnable. DTO immutable có constructor binding nên cần thử đúng Spring version và tên tham số khi dùng với forms; những forms phức tạp có collection indexes thường thuận tiện hơn với input bean riêng. Điều cần ghi nhớ là vị trí `BindingResult` **phải ngay sau** argument được validate.

### 6.1. Native handler method validation là cơ chế khác

Spring Framework 6.1+ hỗ trợ native method validation cho direct constraints trên method parameters, ví dụ:

~~~java
@GetMapping("/api/orders/limits")
String limits(@RequestParam @Min(1) int count) {
    return "ok";
}
~~~

Khi lỗi, MVC có thể ném `HandlerMethodValidationException`, với cách nhóm kết quả theo method parameters. Nó **không** giống `MethodArgumentNotValidException` của một DTO được validate riêng. Thêm direct `@NotNull` vào `@Valid @RequestBody` có thể khiến method validation được chọn thay vì argument-level validation, theo cấu trúc method signature.

Bộ runnable test của bài **không** đặt direct constraint trên controller method argument để giữ nguyên đường `MethodArgumentNotValidException` cho cả ba loại lỗi.

### 6.2. JSON không giải mã được là lỗi trước validation

Các request như:

~~~text
{"customerName":
~~~

hoặc gửi `"quantity":"abc"` vào field `Integer` trong DTO có thể khiến Jackson không dựng được Java object. Khi đó Spring thường ném `HttpMessageNotReadableException`; **không có guarantee rằng Bean Validation hoặc BindingResult đã chạy**. Chỉ test status 400 không phân biệt được lỗi parse JSON với lỗi `@NotBlank`.

Với `application/x-www-form-urlencoded`, Spring `WebDataBinder` thường có thể gom conversion failure vào `BindingResult` với `typeMismatch`. Với JSON, Jackson deserialization xảy ra trước validation và thường báo một exception khác. Viết tests tách hai đường là quan trọng.

## 7. Project Java 17+ / Spring Boot 3.5.7 có thể chạy

Ta tạo endpoint `POST /api/orders` với ba cấp lỗi. Spring Boot 3.5.7 quản lý Spring Framework 6.2.x và Jakarta Bean Validation provider (thường Hibernate Validator). Mọi lỗi sau khi body đã deserialize thành `CreateOrderRequest` sẽ có `BindingResult` trong `MethodArgumentNotValidException` và được một `@RestControllerAdvice` chuyển thành JSON ổn định.

### 7.1. Cấu trúc tệp

~~~text
spring-validation-tests/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/validation/
    │   │   ├── Application.java
    │   │   ├── ShippingAddress.java
    │   │   ├── OrderLine.java
    │   │   ├── CreateOrderRequest.java
    │   │   ├── ValidPeriod.java
    │   │   ├── ValidPeriodValidator.java
    │   │   ├── OrderController.java
    │   │   └── ValidationAdvice.java
    │   └── resources/application.properties
    └── test/java/com/example/validation/
        ├── OrderValidationHttpTest.java
        ├── JakartaValidationTest.java
        └── SpringErrorsTest.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-validation-tests</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Không cần `spring-boot-starter-aop` cho ví dụ này; đây là **argument-level validation**, không phải service AOP method validation. `spring-boot-starter-web` tích hợp Jackson (bao gồm Java Time support qua dependency managed) cho JSON ISO ngày; validation starter cung cấp Jakarta provider.

### 7.3. Application.java

~~~java
package com.example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 7.4. ShippingAddress.java

~~~java
package com.example.validation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record ShippingAddress(
        @NotBlank String street,
        @NotBlank String city,
        @NotBlank
        @Pattern(regexp = "[0-9]{5}")
        String postalCode) {
}
~~~

`city=""` vi phạm `@NotBlank`. `postalCode="XYZ"` vi phạm `@Pattern`. Với `null` postalCode, `@NotBlank` lỗi còn `@Pattern` mặc định cho null là hợp lệ, vì vậy hai constraints có trách nhiệm riêng.

### 7.5. OrderLine.java

~~~java
package com.example.validation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record OrderLine(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity) {
}
~~~

Với `quantity=0`, lỗi `Min` trên `lines[0].quantity`. Với `quantity=null`, lỗi `NotNull`. `@NotBlank` trên `sku` không tự chạy nếu root chưa cascade vào phần tử.

### 7.6. CreateOrderRequest.java

~~~java
package com.example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.time.LocalDate;
import java.util.List;

@ValidPeriod
public record CreateOrderRequest(
        @NotBlank String customerName,
        @NotNull @Valid ShippingAddress shippingAddress,
        @NotEmpty List<@NotNull @Valid OrderLine> lines,
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate) {
}
~~~

Cấu trúc này chủ động cho ba cấp:

- `@NotBlank customerName` tạo lỗi một trường.
- `@ValidPeriod` gắn trên root record tạo lỗi toàn đối tượng.
- `@Valid ShippingAddress` và `List<@Valid OrderLine>` cascade để tạo lỗi đường dẫn lồng.
- `@NotNull` trên address, dates và collection element tránh lẫn ý nghĩa “vắng mặt” với “sai field con”.
- `@NotEmpty` trên list đảm bảo có ít nhất một phần tử.

Trong Spring 6.2/Hibernate Validator 8, Jakarta annotations có thể gắn vào các record components như trên. Không dùng `javax.validation.*` cũ của Spring Boot 2.

### 7.7. ValidPeriod.java — custom class-level constraint

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidPeriodValidator.class)
public @interface ValidPeriod {

    String message()
            default "End date must not be before start date";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

Đây là class-level constraint. Không khai báo `@Target(FIELD)` nếu muốn test global ObjectError đúng nghĩa của ví dụ.

### 7.8. ValidPeriodValidator.java

~~~java
package com.example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class ValidPeriodValidator
        implements ConstraintValidator<ValidPeriod, CreateOrderRequest> {

    @Override
    public boolean isValid(
            CreateOrderRequest request,
            ConstraintValidatorContext context) {

        if (request == null
                || request.startDate() == null
                || request.endDate() == null) {
            return true;
        }

        return !request.endDate().isBefore(
                request.startDate());
    }
}
~~~

Nếu `startDate="2026-11-01"` và `endDate="2026-10-31"`, return false. Vì không gọi `disableDefaultConstraintViolation()` hoặc `addPropertyNode(...)`, vi phạm ở **root object**. `LocalValidatorFactoryBean` chuyển thành `ObjectError` trong Spring MVC.

Nếu ngày null, validator này bỏ qua; `@NotNull` của đúng field sẽ báo lỗi. Test riêng điều này để tránh lỗi NPE và để tránh một yêu cầu thiếu cả hai ngày lại nhận message `ValidPeriod` gây hiểu nhầm.

### 7.9. OrderController.java

~~~java
package com.example.validation;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    public record OrderAccepted(
            String result,
            String customerName,
            int lineCount) {
    }

    @PostMapping
    public ResponseEntity<OrderAccepted> create(
            @Valid @RequestBody CreateOrderRequest request) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new OrderAccepted(
                        "created",
                        request.customerName(),
                        request.lines().size()));
    }
}
~~~

Controller không nhận `BindingResult` sau `@RequestBody` và không có direct constraints trên các method arguments khác. Bởi vậy trong Spring MVC, invalid DTO sau deserialize đi qua `MethodArgumentNotValidException`. Request hợp lệ trả HTTP 201. Domain persistence không nằm trong phạm vi bài test validation.

### 7.10. ValidationAdvice.java — gom field/global đúng loại

~~~java
package com.example.validation;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@RestControllerAdvice
public class ValidationAdvice {

    public record FieldIssue(
            String path,
            String code,
            boolean bindingFailure) {
    }

    public record ValidationReport(
            String code,
            List<FieldIssue> fieldErrors,
            List<String> globalErrors) {
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ValidationReport> invalid(
            MethodArgumentNotValidException ex) {

        BindingResult result = ex.getBindingResult();

        List<FieldIssue> fields = result.getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        Objects.toString(
                                error.getCode(), "invalid"),
                        error.isBindingFailure()))
                .sorted(Comparator
                        .comparing(FieldIssue::path)
                        .thenComparing(FieldIssue::code))
                .toList();

        List<String> global = result.getGlobalErrors()
                .stream()
                .map(error -> Objects.toString(
                        error.getCode(), "invalid"))
                .sorted()
                .toList();

        return ResponseEntity.badRequest().body(
                new ValidationReport(
                        "VALIDATION_FAILED",
                        fields,
                        global));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> unreadable(
            HttpMessageNotReadableException ex) {

        return ResponseEntity.badRequest().body(
                Map.of("code", "INVALID_JSON"));
    }
}
~~~

Vì `FieldError extends ObjectError`, bạn không nên map `result.getAllErrors()` thành `globalErrors`. Code này lấy **hai tập riêng**; giữ `path` chỉ cho field errors; chỉ đưa `code` của global errors mà không bịa một field path.

Sắp xếp errors theo `path` rồi `code` giúp contract JSON và tests ổn định bất kể provider trả violations theo thứ tự nào. Response **không** có `error.getRejectedValue()`, stack trace hoặc raw invalid input; điều này giúp giảm nguy cơ lộ dữ liệu nhạy cảm.

`HttpMessageNotReadableException` được xử lý thành một mã riêng `INVALID_JSON`, không được “giả” thành FieldError. Production có thể chuẩn hóa tất cả lỗi vào ProblemDetail/RFC 9457, nhưng bài này dùng response JSON nhỏ để trực quan hóa field và global groups.

### 7.11. application.properties

~~~properties
server.port=8080
spring.mvc.problemdetails.enabled=false
server.error.include-message=never
~~~

Advice tự xử lý hai loại exception để test cấu trúc lỗi ổn định. `spring.mvc.problemdetails.enabled=false` không ngăn ứng dụng dùng `ProblemDetail` nếu muốn sau này; chỉ tránh phụ thuộc Boot auto-config Problem Details trong phạm vi ví dụ.

### 7.12. Chạy ứng dụng và gửi request

~~~bash
mvn spring-boot:run
~~~

Request hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customerName":"Lan",
    "shippingAddress":{
      "street":"12 Main",
      "city":"Ha Noi",
      "postalCode":"12345"
    },
    "lines":[{"sku":"BOOK-1","quantity":2}],
    "startDate":"2026-11-01",
    "endDate":"2026-11-03"
  }'
~~~

HTTP status mong đợi **201 Created**, JSON body:

~~~json
{
  "result": "created",
  "customerName": "Lan",
  "lineCount": 1
}
~~~

Request có ba loại lỗi cùng lúc:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customerName":"",
    "shippingAddress":{
      "street":"12 Main",
      "city":"",
      "postalCode":"12345"
    },
    "lines":[{"sku":"","quantity":2}],
    "startDate":"2026-11-01",
    "endDate":"2026-10-31"
  }'
~~~

HTTP status mong đợi **400 Bad Request**. Các fields sẽ được sort theo path. Body chính:

~~~json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "path": "customerName",
      "code": "NotBlank",
      "bindingFailure": false
    },
    {
      "path": "lines[0].sku",
      "code": "NotBlank",
      "bindingFailure": false
    },
    {
      "path": "shippingAddress.city",
      "code": "NotBlank",
      "bindingFailure": false
    }
  ],
  "globalErrors": ["ValidPeriod"]
}
~~~

Đây là output dự kiến theo contract do `ValidationAdvice` xây dựng; vì không serialize default messages, nội dung không phụ thuộc vào locale. Tên field đường dẫn theo Java DTO. Một client có thể dùng `fieldErrors[].path` để ánh xạ vào form fields và `globalErrors` để hiển thị banner lỗi tổng thể.

## 8. MockMvc test ba loại lỗi tách riêng

Tạo `src/test/java/com/example/validation/OrderValidationHttpTest.java`:

~~~java
package com.example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderValidationHttpTest {

    @Autowired
    MockMvc mvc;

    private static String validJson() {
        return """
                {
                  "customerName":"Lan",
                  "shippingAddress":{
                    "street":"12 Main",
                    "city":"Ha Noi",
                    "postalCode":"12345"
                  },
                  "lines":[
                    {"sku":"BOOK-1","quantity":2}
                  ],
                  "startDate":"2026-11-01",
                  "endDate":"2026-11-03"
                }
                """;
    }

    private org.springframework.test.web.servlet.ResultActions
    postJson(String body) throws Exception {
        return mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body));
    }

    @Test
    void validPayloadReturnsCreated() throws Exception {
        postJson(validJson())
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.result").value("created"))
                .andExpect(jsonPath("$.lineCount").value(1));
    }

    @Test
    void singleFieldErrorIsNotGlobal() throws Exception {
        String body = validJson().replace(
                "\"customerName\":\"Lan\"",
                "\"customerName\":\"\"");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(
                        "VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fieldErrors", hasSize(1)))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].path")
                        .value("customerName"))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].code")
                        .value("NotBlank"))
                .andExpect(jsonPath(
                        "$.fieldErrors[0].bindingFailure")
                        .value(false))
                .andExpect(jsonPath("$.globalErrors", hasSize(0)));
    }

    @Test
    void classLevelErrorIsGlobalNotField()
            throws Exception {

        String body = validJson().replace(
                "\"endDate\":\"2026-11-03\"",
                "\"endDate\":\"2026-10-31\"");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors", hasSize(0)))
                .andExpect(jsonPath("$.globalErrors", hasSize(1)))
                .andExpect(jsonPath("$.globalErrors[0]")
                        .value("ValidPeriod"));
    }

    @Test
    void nestedBeanFieldErrorContainsFullPath()
            throws Exception {

        String body = validJson().replace(
                "\"city\":\"Ha Noi\"",
                "\"city\":\"\"");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors", hasSize(1)))
                .andExpect(jsonPath("$.fieldErrors[0].path")
                        .value("shippingAddress.city"))
                .andExpect(jsonPath("$.fieldErrors[0].code")
                        .value("NotBlank"))
                .andExpect(jsonPath("$.globalErrors", hasSize(0)));
    }

    @Test
    void listElementErrorContainsIndex()
            throws Exception {

        String body = validJson().replace(
                "\"sku\":\"BOOK-1\"",
                "\"sku\":\"\"");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors", hasSize(1)))
                .andExpect(jsonPath("$.fieldErrors[0].path")
                        .value("lines[0].sku"))
                .andExpect(jsonPath("$.fieldErrors[0].code")
                        .value("NotBlank"));
    }

    @Test
    void quantityRuleIsNestedFieldError()
            throws Exception {

        String body = validJson().replace(
                "\"quantity\":2", "\"quantity\":0");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors[0].path")
                        .value("lines[0].quantity"))
                .andExpect(jsonPath("$.fieldErrors[0].code")
                        .value("Min"));
    }

    @Test
    void missingNestedObjectIsItsOwnFieldError()
            throws Exception {

        String body = validJson().replace(
                """
                    "shippingAddress":{
                    "street":"12 Main",
                    "city":"Ha Noi",
                    "postalCode":"12345"
                  }
                """.trim(),
                "\"shippingAddress\":null");

        // Kiểm tra body đã đổi; nếu format khác thì
        // dùng một literal JSON đầy đủ thay vì replace.
        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors[0].path")
                        .value("shippingAddress"))
                .andExpect(jsonPath("$.fieldErrors[0].code")
                        .value("NotNull"));
    }

    @Test
    void missingDateDoesNotTriggerClassLevelRule()
            throws Exception {

        String body = validJson().replace(
                "\"endDate\":\"2026-11-03\"",
                "\"endDate\":null");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors[0].path")
                        .value("endDate"))
                .andExpect(jsonPath("$.fieldErrors[0].code")
                        .value("NotNull"))
                .andExpect(jsonPath("$.globalErrors", hasSize(0)));
    }

    @Test
    void mixedErrorsStayInSeparateArrays()
            throws Exception {

        String body = validJson()
                .replace("\"customerName\":\"Lan\"",
                        "\"customerName\":\"\"")
                .replace("\"city\":\"Ha Noi\"",
                        "\"city\":\"\"")
                .replace("\"sku\":\"BOOK-1\"",
                        "\"sku\":\"\"")
                .replace("\"endDate\":\"2026-11-03\"",
                        "\"endDate\":\"2026-10-31\"");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors", hasSize(3)))
                .andExpect(jsonPath("$.globalErrors", hasSize(1)))
                .andExpect(jsonPath("$.fieldErrors[0].path")
                        .value("customerName"))
                .andExpect(jsonPath("$.fieldErrors[1].path")
                        .value("lines[0].sku"))
                .andExpect(jsonPath("$.fieldErrors[2].path")
                        .value("shippingAddress.city"))
                .andExpect(jsonPath("$.globalErrors[0]")
                        .value("ValidPeriod"));
    }

    @Test
    void malformedJsonIsNotBeanValidation()
            throws Exception {

        postJson("{")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_JSON"))
                .andExpect(jsonPath("$.fieldErrors")
                        .doesNotExist());
    }

    @Test
    void invalidDateTextIsDeserializationFailure()
            throws Exception {

        String body = validJson().replace(
                "\"startDate\":\"2026-11-01\"",
                "\"startDate\":\"not-a-date\"");

        postJson(body)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }
}
~~~

**Lưu ý sửa test `missingNestedObject...`:** phương pháp `String.replace` dựa vào đúng chuỗi/whitespace của Java text block; để test bền vững, tốt nhất dùng `ObjectMapper` và `ObjectNode` hoặc một JSON literal đầy đủ. Cách thay một đoạn JSON nhiều dòng ở trên chỉ nhằm mô tả sự khác nhau giữa `shippingAddress=null` và `shippingAddress.city=""`; nếu bạn chỉnh format của `validJson()`, hãy đồng thời sửa/loại bỏ thao tác replace phụ thuộc whitespace. Các tests còn lại replace theo token ngắn ổn định.

### 8.1. Vì sao chỉ so paths/codes thay vì defaultMessage?

Nếu test phụ thuộc `"must not be blank"`, việc đổi locale sang tiếng Việt hoặc nâng phiên bản Hibernate Validator có thể khiến test fail dù rule và contract vẫn đúng. `FieldError.getCode()` (như `NotBlank`, `Min`) và đường dẫn `getField()` thường phù hợp hơn cho test cấu trúc.

Vẫn cần một **test riêng** cho MessageSource/i18n nếu sản phẩm yêu cầu đúng câu lỗi tiếng Việt. Không trộn test mã lỗi với test bản dịch.

### 8.2. Vì sao cần test global empty?

Nếu chỉ:

~~~java
.andExpect(status().isBadRequest())
~~~

thì việc `@ValidPeriod` bị gắn nhầm sang `endDate` vẫn có thể trả 400. Test:

~~~java
.andExpect(jsonPath("$.fieldErrors", hasSize(0)))
.andExpect(jsonPath("$.globalErrors[0]")
        .value("ValidPeriod"))
~~~

xác định **đúng cấp lỗi**. Trong sản phẩm có UI, lỗi global có thể hiển thị ở đầu form, còn lỗi field hiển thị cạnh ô nhập tương ứng.

## 9. Test Jakarta Validation trực tiếp, không cần HTTP

Tạo `src/test/java/com/example/validation/JakartaValidationTest.java`:

~~~java
package com.example.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.time.LocalDate;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class JakartaValidationTest {

    @Autowired
    Validator validator;

    private static CreateOrderRequest request(
            String name,
            String city,
            String sku,
            LocalDate start,
            LocalDate end) {

        return new CreateOrderRequest(
                name,
                new ShippingAddress(
                        "12 Main", city, "12345"),
                List.of(new OrderLine(sku, 2)),
                start,
                end);
    }

    @Test
    void validatesOneField() {
        var input = request(
                "", "Ha Noi", "BOOK-1",
                LocalDate.parse("2026-11-01"),
                LocalDate.parse("2026-11-03"));

        Set<ConstraintViolation<CreateOrderRequest>>
                result = validator.validate(input);

        assertEquals(1, result.size());
        assertTrue(result.stream().anyMatch(v ->
                v.getPropertyPath().toString()
                        .equals("customerName")));
    }

    @Test
    void classLevelViolationHasEmptyRootPath() {
        var input = request(
                "Lan", "Ha Noi", "BOOK-1",
                LocalDate.parse("2026-11-01"),
                LocalDate.parse("2026-10-31"));

        var result = validator.validate(input);

        assertEquals(1, result.size());
        assertTrue(result.stream().anyMatch(v ->
                v.getPropertyPath().toString().isEmpty()
                && v.getConstraintDescriptor()
                        .getAnnotation()
                        .annotationType()
                        .equals(ValidPeriod.class)));
    }

    @Test
    void nestedBeanPathIncludesParent() {
        var input = request(
                "Lan", "", "BOOK-1",
                LocalDate.parse("2026-11-01"),
                LocalDate.parse("2026-11-03"));

        var result = validator.validate(input);

        assertEquals(1, result.size());
        assertTrue(result.stream().anyMatch(v ->
                v.getPropertyPath().toString()
                        .equals("shippingAddress.city")));
    }

    @Test
    void nestedListPathIncludesIndex() {
        var input = request(
                "Lan", "Ha Noi", "",
                LocalDate.parse("2026-11-01"),
                LocalDate.parse("2026-11-03"));

        var result = validator.validate(input);

        assertEquals(1, result.size());
        assertTrue(result.stream().anyMatch(v ->
                v.getPropertyPath().toString()
                        .equals("lines[0].sku")));
    }

    @Test
    void absentDateLeavesCrossFieldValidatorSilent() {
        var input = request(
                "Lan", "Ha Noi", "BOOK-1",
                LocalDate.parse("2026-11-01"),
                null);

        var result = validator.validate(input);

        assertEquals(1, result.size());
        assertTrue(result.stream().allMatch(v ->
                v.getPropertyPath().toString()
                        .equals("endDate")));
    }
}
~~~

Bộ tests này cô lập Bean Validation provider khỏi HTTP argument resolver, Jackson và advice. Nó trả `Set<ConstraintViolation<?>>`; **không** kiểm tra trực tiếp Spring `BindingResult.getGlobalErrors()`. Dùng song song với MockMvc để phân biệt rule engine hoạt động đúng và integration với MVC hoạt động đúng.

## 10. Test Spring Errors / BindingResult trực tiếp

Tạo `src/test/java/com/example/validation/SpringErrorsTest.java`:

~~~java
package com.example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.validation.MapBindingResult;

import java.util.HashMap;

import static org.junit.jupiter.api.Assertions.*;

class SpringErrorsTest {

    @Test
    void rejectAndRejectValueAreDifferent() {
        var result = new MapBindingResult(
                new HashMap<String, Object>(),
                "createOrderRequest");

        result.rejectValue(
                "customerName",
                "name.required");

        result.reject(
                "period.invalid");

        assertEquals(2, result.getErrorCount());
        assertEquals(1, result.getFieldErrorCount());
        assertEquals(1, result.getGlobalErrorCount());

        assertTrue(result.hasFieldErrors("customerName"));
        assertEquals("name.required",
                result.getFieldError("customerName")
                        .getCode());

        assertTrue(result.hasGlobalErrors());
        assertEquals("period.invalid",
                result.getGlobalError().getCode());

        assertEquals(2, result.getAllErrors().size());
    }

    @Test
    void nestedPathIsPrefixedAndRestored() {
        var result = new MapBindingResult(
                new HashMap<String, Object>(),
                "createOrderRequest");

        result.pushNestedPath("shippingAddress");
        try {
            result.rejectValue("city", "city.required");
        } finally {
            result.popNestedPath();
        }

        result.rejectValue(
                "lines[0].sku", "sku.required");

        assertEquals(2, result.getFieldErrorCount());

        assertEquals("shippingAddress.city",
                result.getFieldError(
                        "shippingAddress.city")
                        .getField());

        assertEquals("lines[0].sku",
                result.getFieldError(
                        "lines[0].sku")
                        .getField());

        assertEquals(0, result.getGlobalErrorCount());
    }
}
~~~

`MapBindingResult` giúp test riêng cơ chế ghi lỗi của Spring trên một map, không cần MVC context và cũng không cần Hibernate Validator. `reject(...)` thêm global error; `rejectValue("field",...)` thêm field error, respect nested path.

Tổng bộ dự án có **18 test methods**: 11 kiểm thử HTTP, 5 kiểm thử Jakarta và 2 kiểm thử Spring Errors. Không khẳng định số lượng violations tùy ý trên một case có nhiều constraints, trừ khi fixture được thiết kế để chỉ một rule thất bại.

Chạy tất cả:

~~~bash
mvn test
~~~

Hoặc chạy từng lớp:

~~~bash
mvn -Dtest=OrderValidationHttpTest test
mvn -Dtest=JakartaValidationTest test
mvn -Dtest=SpringErrorsTest test
~~~

Ví dụ được soạn để biên dịch với Java 17+ và Spring Boot 3.5.7; **chưa thực thi Maven trong môi trường soạn README**. Khi triển khai thật, dùng bản vá được duy trì, đặc biệt với các advisory bảo mật liên quan Jackson, Spring MVC và data binding.

## 11. Cải tiến test: dùng ObjectMapper thay String.replace

`String.replace` là lựa chọn dễ đọc với fixture nhỏ và chuỗi token không đổi. Đối với test suite lớn, thao tác đó có thể không sửa được JSON nếu khoảng trắng hoặc cách serialize thay đổi. Nên dùng Jackson `ObjectMapper` và `ObjectNode` để mutate fixture có cấu trúc:

~~~java
ObjectMapper mapper = new ObjectMapper();
ObjectNode root = (ObjectNode) mapper.readTree(
        validJson());

root.put("customerName", "");
((ObjectNode) root.path("shippingAddress"))
        .put("city", "");

ArrayNode lines = (ArrayNode) root.path("lines");
((ObjectNode) lines.get(0)).put("sku", "");

String body = mapper.writeValueAsString(root);
~~~

Đây là **snippet độc lập về thao tác JSON** (cần imports Jackson và gọi trong test class có method `validJson()`). Khi test cần Jackson deserialize `LocalDate` trực tiếp thành Java object, nhớ Java Time module; nhưng snippet ở đây chỉ xử lý `JsonNode` nên không cần deserialize ngày thành `LocalDate`.

Để test `shippingAddress=null` chắc chắn, có thể làm:

~~~java
ObjectNode root = (ObjectNode) mapper.readTree(
        validJson());

root.putNull("shippingAddress");

String body = mapper.writeValueAsString(root);
~~~

Cách này tránh test “PASS giả” vì `replace` không tìm thấy đoạn nhiều dòng chính xác.

### Khi nào nên dùng fixtures riêng?

- Nếu mỗi test cần một biến thể dễ đọc: tạo `src/test/resources/json/valid-order.json`, `blank-name.json`, `invalid-period.json`, `nested-city.json`.
- Nếu chỉ đổi một giá trị từ baseline: dùng `ObjectMapper`/`ObjectNode` để clone/mutate JSON.
- Nếu đang kiểm tra lỗi decode: gửi **raw malformed string**, đừng dùng `ObjectMapper` tạo body vì mapper sẽ ngăn tạo JSON hỏng.
- Nếu cần assert lỗi theo thứ tự: sort ở API layer hoặc dùng matcher không phụ thuộc thứ tự, không gọi `violations.iterator().next()` tùy tiện.

## 12. Test nhiều lỗi cùng lúc và đường dẫn chính xác

### 12.1. Một field có thể có nhiều errors

Một field có cả `@NotBlank` và `@Pattern` có thể có nhiều constraint violations nếu dữ liệu đồng thời vi phạm. Khi đó:

~~~java
errors.getFieldErrors("postalCode")
~~~

có thể có nhiều hơn một `FieldError`. Đừng dùng mỗi `getFieldError("postalCode")` rồi mặc định nó đại diện mọi lỗi. Kiểm tra **tập codes** hoặc policy “hiển thị lỗi đầu tiên” rõ ràng.

### 12.2. Global và field có thể đồng thời thất bại

Với một input vừa `customerName=""` vừa `endDate < startDate`, BindingResult có cả `FieldError("customerName")` và `ObjectError("createOrderRequest")`. Một response chỉ serialize `getFieldErrors()` sẽ đánh mất class-level rule; một response chỉ serialize `getAllErrors()` nhưng không lưu loại sẽ khiến client khó đặt lỗi đúng UI.

### 12.3. Nested collections với nhiều phần tử

Một list:

~~~json
{
  "lines": [
    {"sku":"OK-1","quantity":2},
    {"sku":"","quantity":0}
  ]
}
~~~

có thể tạo:

~~~text
lines[1].sku       → NotBlank
lines[1].quantity  → Min
~~~

Nếu thay đổi thứ tự list, các indexes đổi theo. Đây là **path phụ thuộc input shape**, không nên coi index là ID nghiệp vụ vĩnh viễn. Với batch edits, một client có thể cần thêm item key/UUID trong DTO để khớp lỗi sau khi reorder.

### 12.4. Nested property path ở Form khác JSON

Form URL-encoded thường có tên parameters:

~~~text
shippingAddress.city=
lines[0].sku=
lines[0].quantity=0
~~~

Spring `WebDataBinder` dùng đường dẫn property. Có thể có lỗi conversion `typeMismatch` khi format sai. Với JSON, Jackson dựng object graph trước khi Spring Bean Validation chạy. Thế nên dù hai request biểu diễn cùng data, exception class và thời điểm thất bại có thể khác.

## 13. Kiểm thử validation groups

`@Validated(Group.class)` cho phép chọn các nhóm constraint theo use case. Một test ở nhóm Default không nhất thiết chạy các constraints chỉ thuộc nhóm khác.

Ví dụ marker:

~~~java
public interface FinalSubmission {
}
~~~

Một field:

~~~java
@NotBlank(groups = FinalSubmission.class)
private String approvalReason;
~~~

Với validation thuần:

~~~java
validator.validate(
        request,
        FinalSubmission.class);
~~~

Đây là các snippets độc lập, không thuộc DTO demo. Nếu test dùng default group nhưng muốn assert lỗi của `FinalSubmission`, bạn sẽ không thấy lỗi; điều đó là behavior đúng, không phải Spring bỏ sót validation.

Khi dùng Spring MVC `@Validated(FinalSubmission.class)` trên argument, cần xem method-level vs argument-level validation và default groups. Nếu muốn chạy cả `Default` và custom group, chọn cả hai hoặc thiết kế group sequence phù hợp, rồi viết test cho đúng contract.

## 14. Test message codes và đa ngôn ngữ

Một `FieldError` có:

~~~text
NotBlank.createOrderRequest.customerName
NotBlank.customerName
NotBlank.java.lang.String
NotBlank
~~~

Đây là ví dụ codes theo `DefaultMessageCodesResolver`; danh sách thực tế có thể khác nếu objectName/type/MessageCodesResolver được cấu hình khác. Global error có thể có:

~~~text
ValidPeriod.createOrderRequest
ValidPeriod
~~~

Nếu ứng dụng dùng `messages_vi.properties`, có thể định nghĩa:

~~~properties
NotBlank.createOrderRequest.customerName=Cần nhập tên người mua
NotBlank.createOrderRequest.shippingAddress.city=Cần nhập thành phố
ValidPeriod.createOrderRequest=Ngày kết thúc không được trước ngày bắt đầu
~~~

Để kiểm thử bản dịch, resolve `ObjectError`/`FieldError` bằng `MessageSource.getMessage(error, locale)`:

~~~java
String localized = messageSource.getMessage(
        error, Locale.forLanguageTag("vi"));
~~~

Snippet cần import `MessageSource`, `ObjectError` và `Locale`, biến `error` là instance tương ứng. Lưu ý Jakarta `ValidationMessages*.properties` (constraint message interpolation) khác Spring `messages*.properties` (FieldError/ObjectError MessageSource), dù chúng có thể được tích hợp có chủ đích qua `LocalValidatorFactoryBean`.

Nên tách test:

1. **Cấu trúc:** path, code, global/field group, HTTP status.
2. **Ngôn ngữ:** message cho `vi`/`en`, fallback và placeholder replacement.

Không hardcode câu tiếng Anh từ Hibernate Validator trong test xác nhận logic validation.

## 15. Bảo mật và tính ổn định của lỗi

### 15.1. Không echo rejected values

`FieldError.getRejectedValue()` có thể chứa dữ liệu nhạy cảm. Không trả body kiểu:

~~~json
{
  "path": "password",
  "rejectedValue": "secret-user-input"
}
~~~

Bài này chỉ trả `path`, `code` và `bindingFailure`. Trong production, message có thể được dịch ở server hoặc client; cả hai cách cần quy định contract và escaping.

### 15.2. Chống mass assignment ở form

Một test về `@ModelAttribute` không chỉ kiểm tra validation. Nếu form DTO có setter nhạy cảm như `role`/`status`, binder có thể gán từ request. Dùng DTO chỉ có editable fields, `WebDataBinder.setAllowedFields` và khi phù hợp `setDeclarativeBinding(true)` (Spring 6.1+). Đây là **kiểm thử an toàn binding**, khác với kiểm thử `@NotBlank`.

### 15.3. Giới hạn nested collection indexes

Một request form có thể cố gửi `lines[1000000].sku` để kích hoạt auto-grow hoặc tiêu thụ tài nguyên. Với binder, đặt collection auto-grow limit theo chính sách, giới hạn request size/line count và cập nhật bản vá Spring. Với JSON, hạn chế kích thước body, số phần tử, độ sâu và kiểm tra nghiệp vụ trước khi xử lý nặng. Không để việc test path lồng dẫn đến một API có thể bị DoS qua dữ liệu quá lớn.

### 15.4. Không làm lộ class name và SQL

Error response chuẩn hóa không được gửi `ex.toString()` hay stack trace trong `detail`. Test client code/status thay vì internal exception messages, đồng thời đảm bảo logs chứa correlation ID và thông tin cần thiết nhưng không lộ secrets.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Test HTTP 400 PASS nhưng global error không có | Chỉ assert status | Assert `getGlobalErrors` hoặc JSON `globalErrors` |
| Class-level rule được đưa vào FieldError | Custom validator dùng `addPropertyNode` | Giữ default class-level violation nếu muốn global |
| `shippingAddress.city` không báo lỗi | Thiếu `@Valid` ở cạnh root → address | Thêm cascade và test nested |
| `shippingAddress=null` không báo lỗi | Chỉ có `@Valid`, không có `@NotNull` | Thêm `@NotNull` trên property |
| `lines[0].sku` không báo lỗi | Không cascade vào list elements | `List<@Valid OrderLine>` và test path |
| List null element không báo lỗi | Cascade bỏ qua null | Dùng `@NotNull` type-use cho element |
| Test chỉ lấy `getFieldError()` | Bỏ các lỗi còn lại | Dùng `getFieldErrors()` và kiểm tập codes |
| Test phụ thuộc thứ tự violations | Set không bảo đảm thứ tự | Sort hoặc assert không phụ thuộc vị trí |
| Test message tiếng Anh thất bại theo locale | Dùng defaultMessage để test logic | Kiểm `code`/`path`, test i18n riêng |
| `@Valid` trên root controller nhưng controller vẫn chạy | `BindingResult` ngay sau argument hoặc validation không kích hoạt | Kiểm signature và Spring setup |
| Đôi khi gặp `HandlerMethodValidationException` | Thêm direct constraint trên method | Nhận diện native validation Spring 6.1+ |
| JSON malformed không có FieldError | Jackson lỗi trước Bean Validation | Test `HttpMessageNotReadableException` |
| Form `quantity=abc` khác JSON `quantity="abc"` | Binder và Jackson hai pipelines khác | Test độc lập theo content type |
| Nested field hiển thị `city` nhưng test yêu cầu prefix | Test dùng path thiếu cha | Assert `shippingAddress.city` |
| `getAllErrors()` toàn ObjectError nên mất phân biệt | `FieldError extends ObjectError` | Tách `getFieldErrors()` và `getGlobalErrors()` |
| Global rule NPE khi ngày null | Cross-field validator không guard null | Null guard, để @NotNull báo field error |
| @Validated group không thấy rule | Nhóm test không phù hợp | Chọn đúng groups |
| JSON bị parse sai LocalDate | Chuỗi ngày không theo ISO/config | Kiểm Jackson Java Time và date format |
| Bản dịch không tìm thấy mã lỗi | objectName/field path thay đổi | In `getCodes()` trong test rồi cập nhật bundle |
| List index path lạ trong Provider khác | Container element metadata khác | Kiểm đúng path ở Jakarta vs Spring MVC |
| Lộ invalid password trong error JSON | Serialize rejectedValue | Chỉ trả code/path, không echo input |

## 17. Chiến lược test trong dự án thật

Để vừa nhanh vừa tin cậy, chia tests theo lớp:

| Lớp test | Dùng gì | Khẳng định |
| --- | --- | --- |
| Unit Spring error holder | `MapBindingResult` / `BeanPropertyBindingResult` | `reject` vs `rejectValue`, nested prefixes, counts |
| Jakarta constraint test | `jakarta.validation.Validator` | Rule logic, default/root path, cascade, groups |
| Spring MVC integration | `MockMvc` với validation provider | Deserialization, annotation resolution, HTTP status, BindingResult adaptation |
| API contract | MockMvc hoặc integration HTTP client | Field/global JSON shape, stable code/path, localization |
| Security & robustness | MockMvc/full app | Không lộ rejected values, giới hạn size, không cập nhật dữ liệu khi invalid |

**Đặt một test cho mỗi loại lỗi**, sau đó thêm test “mixed” để chứng minh Spring không làm rơi lỗi khi nhiều constraint thất bại trong cùng request. Trong hệ thống có service/persistence, test invalid request phải xác nhận **không có side effect** (không tạo bản ghi, không gửi event, không đặt hàng).

### Kiểm tra nhanh khi test thất bại

1. In `BindingResult.getObjectName()` và `getAllErrors()` trong môi trường test, nhưng tránh log `rejectedValue` nhạy cảm.
2. Xác nhận `@Valid` trên controller argument và trên cạnh nested.
3. Xác nhận Jakarta provider có trên classpath (Spring Boot validation starter).
4. Kiểm tra class-level constraint `@Target(TYPE)` và validator không vô tình gắn `addPropertyNode`.
5. Phân biệt exception JSON parse với exception validation.
6. Kiểm tra tên root object và actual field paths.
7. Kiểm tra null guard, group selection và collection element constraints.
8. Nếu test dùng JSON string replacement, xác nhận chuỗi được thay thật; ưu tiên ObjectNode khi fixture lớn.
9. Đừng dựa trên nội dung default message hoặc thứ tự không được bảo đảm.
10. Nếu cần audit API, test cả response schema và dữ liệu cuối.

## 18. Bài tập tự luyện

**1. Field vs global.** Gửi `customerName=""` và `endDate < startDate` riêng biệt. Kiểm tra số field/global errors của mỗi case và giải thích vì sao HTTP status của chúng có thể giống nhau.

**2. Class-level error.** Trong `ValidPeriodValidator`, dùng `addPropertyNode("endDate")` để chuyển lỗi sang field. Sửa test và giải thích tác động đến UI/contract.

**3. Nested bean.** Xóa `@Valid` khỏi `shippingAddress` rồi chạy test thành phố rỗng. Lỗi nào biến mất? `@NotNull` của address có giúp kiểm tra city không?

**4. List element.** Gửi hai lines, phần tử thứ hai có `sku=""`. Assert path `lines[1].sku` mà không dựa vào thứ tự các vi phạm khác.

**5. Missing nested object.** So sánh lỗi `shippingAddress=null` với `shippingAddress.city=""`. Khi nào path là `shippingAddress`, khi nào là `shippingAddress.city`?

**6. JSON khác form.** Thử gửi `quantity="abc"` qua JSON và gửi `quantity=abc` qua form có binder. Tại sao exception và metadata lỗi có thể khác nhau?

**7. Spring Errors.** Viết một Spring `Validator` gọi `errors.reject("order.invalid")` và `errors.rejectValue("customerName","name.required")`; kiểm tra `getAllErrors()`, `getFieldErrorCount()` và `getGlobalErrorCount()`.

**8. Localization.** Tạo `messages_vi.properties` cho mã `ValidPeriod.createOrderRequest` và `NotBlank.createOrderRequest.customerName`; kiểm tra code ổn định nhưng câu chữ thay theo Locale.

**9. Groups.** Gắn constraint của postalCode vào custom group. Chứng minh nhóm Default không chạy constraint này, rồi dùng `@Validated(...)` hoặc direct Jakarta Validator groups để kích hoạt.

**10. Bảo mật.** Thêm field password vào nested input, cố đưa `rejectedValue` vào response và viết test phát hiện chuỗi nhạy cảm; sửa mapper để chỉ trả code/path.

## Kết luận

Ba câu cần nhớ:

~~~text
Lỗi một trường      → FieldError("customerName")
Lỗi toàn đối tượng  → ObjectError("createOrderRequest")
Lỗi đường dẫn lồng  → FieldError("shippingAddress.city")
                       FieldError("lines[0].sku")

BindingResult.getFieldErrors()
BindingResult.getGlobalErrors()
BindingResult.getAllErrors()
~~~

**Test status 400 chưa đủ**. Hãy xác minh đúng **loại**, **mã**, **đường dẫn**, **số lượng**, **cấp lỗi** và không mất lỗi khi có nhiều violations. Tách Jakarta constraint tests, Spring Errors tests và MockMvc integration tests giúp chẩn đoán nhanh liệu vấn đề nằm ở rule, cascade, error adaptation, JSON deserialization hay HTTP rendering.

## Tài liệu tham khảo

- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Bean Validation integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Error Code Resolution](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [Spring Framework — Errors API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/Errors.html)
- [Spring Framework — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework — ObjectError API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/ObjectError.html)
- [Spring Framework — MethodArgumentNotValidException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/MethodArgumentNotValidException.html)
- [Spring Framework — ResponseEntityExceptionHandler](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Jakarta Bean Validation 3.0 specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Hibernate Validator — Reference Guide](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/)

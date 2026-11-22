# Constraint không chạy do thiếu provider hoặc thiếu điểm kích hoạt

Một lỗi rất thường gặp trong Spring Framework là code đã có `@NotBlank`, `@Min`, `@NotNull` hoặc `@Valid`, ứng dụng vẫn khởi động, nhưng dữ liệu rõ ràng không hợp lệ lại **không tạo lỗi validation**. Chẳng hạn client gửi `{"title":"","quantity":0}` mà endpoint vẫn xử lý; hoặc method của service nhận chuỗi rỗng dù tham số khai báo `@NotBlank`.

Phải phân biệt **hai nhóm nguyên nhân**:

1. **Thiếu hoặc không tải được Bean Validation provider**: code nhìn thấy annotation API `jakarta.validation.*` nhưng runtime không có implementation tương thích, ví dụ Hibernate Validator, hoặc dùng lẫn các thư viện `javax.validation` cũ với Jakarta API.
2. **Có provider nhưng thiếu điểm kích hoạt**: chẳng hạn controller quên `@Valid` trên `@RequestBody`; service không có `@Validated` cấp class hoặc gọi không qua Spring AOP proxy; nested DTO không có `@Valid`; custom Spring `Validator` chưa được đăng ký/chạy; hoặc validation group không chứa constraint mong đợi.

Cũng có trường hợp **validation đã chạy nhưng lỗi bị xử lý sai**: handler có `BindingResult` rồi bỏ qua `hasErrors()`, hoặc `@RestControllerAdvice` đổi một lỗi 400 thành response thành công. Bởi vậy, cần một quy trình chẩn đoán tách biệt **provider → constraint metadata → trigger → kết quả/exception → HTTP mapping**.

Bài thuộc nhóm **Chẩn đoán** của module **Spring Framework — validation-data-binding**. Ví dụ sử dụng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Jakarta Validation và Spring MVC Servlet**. Phiên bản được chọn để có cùng API nhất quán; không mặc định đây là bộ phiên bản mới nhất trong mọi dự án.

## 1. Sơ đồ nguyên nhân

~~~text
Annotation: @NotBlank, @Min, @Valid
             |
             v
[1] Namespace + classpath
    jakarta.validation.* đúng phiên bản?
             |
             v
[2] Provider
    Hibernate Validator/implementation khả dụng?
             |
             v
[3] Entry point
    MVC: @Valid/@Validated trên argument?
    Service: @Validated + Spring proxy?
    Manual: jakartaValidator.validate(...)?
             |
             v
[4] Group + cascade + type
    Default/Custom Group?
    @Valid trên nested property?
    Constraint hỗ trợ kiểu field?
             |
             v
[5] ConstraintValidator thực thi
    Có violation thật sự?
             |
             v
[6] Spring adaptation
    BindingResult, MethodArgumentNotValidException,
    HandlerMethodValidationException,
    ConstraintViolationException...
             |
             v
[7] Response/logging
    Handler có nuốt lỗi hoặc trả HTTP 200 không?
~~~

**Annotation không phải executable Java check.** Có annotation `@NotNull` trên field không đồng nghĩa JVM sẽ tự chạy nó khi gọi setter hay tạo record. Phải có runtime Bean Validation provider và lời gọi đúng entry point.

### Bảng phân loại nhanh

| Triệu chứng | Khả năng cao | Bước kiểm tra |
|---|---|---|
| Tất cả Jakarta constraints đều không tạo violation | Provider thiếu/incompatible | Runtime dependencies, direct Jakarta validator test |
| Provider test trực tiếp PASS, HTTP invalid vẫn qua | Thiếu `@Valid` trên MVC argument | Controller signature, MockMvc |
| Field root sai có lỗi, nested email sai không | Thiếu nested `@Valid` | DTO property/record component |
| Service method không chặn input sai | `@Validated`/AOP/proxy chưa kích hoạt | Inject Spring-managed service bean |
| Self-invocation không có exception | Internal method bypass proxy | Test external vs internal call |
| Có HTTP 400 dù provider không chạy | Parse/conversion failure | Loại exception thực tế |
| `@Size` không báo lỗi với null | Null hợp lệ với constraint này | `@NotNull` bổ sung |
| Constraint custom không chạy | Sai `@Constraint`, retention, target, groups | Metadata và provider bootstrap |
| Annotation `javax.validation` trong Boot 3 | Namespace legacy | Chuyển sang `jakarta.validation` |
| Handler được gọi dù form sai | Có `BindingResult`, chưa xử lý | `errors.hasErrors()` |

## 2. Phân biệt ba loại Validator

### Jakarta Bean Validation API

~~~java
jakarta.validation.Validator
~~~

Có phương thức `validate(T object, Class<?>... groups)` trả `Set<ConstraintViolation<T>>`. Nó do một provider thực thi; annotation `@NotBlank`/`@Min` là metadata để provider xử lý.

### Spring Validator

~~~java
org.springframework.validation.Validator
~~~

Có `supports(Class<?>)` và `validate(Object, Errors)`. Lập trình viên tự viết logic, gọi `errors.rejectValue(...)` hoặc `errors.reject(...)`. Nó **không tự tìm mọi annotation Jakarta** trừ khi dùng adapter phù hợp.

### Spring LocalValidatorFactoryBean

~~~java
org.springframework.validation.beanvalidation.LocalValidatorFactoryBean
~~~

Đây là adapter tích hợp Spring và Jakarta Bean Validation: cung cấp các khả năng Jakarta `Validator`/`ValidatorFactory` và hỗ trợ Spring validation contracts, chuyển `ConstraintViolation` thành `FieldError`/`ObjectError` qua `Errors`. Spring MVC có thể đăng ký global validator khi provider có mặt.

**Lỗi nhập nhầm interface:** nếu unit test `jakartaValidator.validate(badDto)` cần một `Set<ConstraintViolation<...>>`, đừng import `org.springframework.validation.Validator` rồi chờ phương thức cùng signature. Cùng tên ngắn `Validator` không đồng nghĩa hai contract giống nhau.

## 3. Chỉ có API không đủ: phải có provider

Một project Spring Boot 3.5 dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-validation` đưa provider phổ biến như Hibernate Validator vào runtime dependency graph phù hợp với Boot BOM. Thư viện `jakarta.validation-api` riêng chỉ cung cấp annotation và interfaces, **không đủ để chứng minh có implementation chạy được**.

Kiểm tra Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
    --configuration runtimeClasspath \
    --dependency hibernate-validator
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --configuration runtimeClasspath --dependency hibernate-validator
~~~

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.hibernate.validator
~~~

Tập trung vào **runtimeClasspath của đúng module deploy**, không chỉ compileClasspath của một thư viện chứa DTO. Nếu provider ở `testImplementation` nhưng không có ở production runtime, unit tests có thể chạy trong khi ứng dụng deploy thiếu dependency. Nếu được đánh dấu `compileOnly`, cũng có nguy cơ runtime không chứa provider.

### Provider bootstrap

~~~java
try (jakarta.validation.ValidatorFactory factory =
        jakarta.validation.Validation
            .buildDefaultValidatorFactory()) {

    jakarta.validation.Validator validator =
        factory.getValidator();

    // validator.validate(invalidFixture)
}
~~~

Đây là snippet trong method. Khi runtime không có provider khả dụng, bootstrap có thể ném `NoProviderFoundException` (thuộc `jakarta.validation`), hoặc `ValidationException` khác nếu cấu hình provider hỏng.

**Không khẳng định mọi ứng dụng thiếu provider đều ném cùng exception ở startup.** Hành vi phụ thuộc setup và việc Bean Validation có được khởi tạo bắt buộc hay không. Một số cấu hình MVC có validator tùy chọn không làm validation; cách đáng tin là **thử direct provider bootstrap và dùng fixture chắc chắn sai**.

### Xác minh provider thực sự có tác dụng

~~~java
public record Sample(
    @jakarta.validation.constraints.NotBlank
    String name) {
}

Sample bad = new Sample("");
var violations = validator.validate(bad);
~~~

Đây là snippet có biến `validator` phù hợp. Nếu provider hoạt động và Default group được dùng, `violations` chứa một lỗi cho `name`. Nếu result vẫn rỗng, xem metadata/namespace/group và provider; không ngay lập tức đổ lỗi cho Spring MVC.

## 4. Spring Boot 2 sang 3: `javax` khác `jakarta`

Với **Spring Boot 3 / Framework 6**, annotation tương ứng thuộc:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
~~~

Thế hệ Spring Boot 2 sử dụng:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
~~~

Đừng giữ legacy `javax.validation-api` trong Boot 3 rồi tin rằng Jakarta provider tự động hiểu mọi constraint javax. Khi migration phải cập nhật **cả** DTO, controller, custom constraints, `ConstraintValidator`, tests, validation groups và transitive dependencies.

**Một đoạn code legacy có thể vẫn compile** vì cả hai APIs vô tình có trong classpath; điều đó không chứng minh Spring Boot 3 runtime đang xử lý annotations legacy.

### Checklist migration

- Xem import của `@Valid` trên handler.
- Xem import các constraint annotations trên DTO.
- Xem import `Constraint`, `Payload`, `ConstraintValidator` trong custom annotations.
- Kiểm tra phiên bản Hibernate Validator được BOM chọn.
- Loại hoặc cách ly dependency Jakarta/Javax không tương thích.
- Xác nhận smoke test `jakarta.validation.Validator.validate(invalidDto)` chạy trên build artifact cuối.

## 5. Điểm kích hoạt ở Spring MVC

### Có `@Valid` trên controller argument

~~~java
@PostMapping("/tickets")
public TicketReply create(
        @Valid @RequestBody TicketRequest request) {
    // ...
}
~~~

Khi request JSON được đọc và chuyển thành `TicketRequest`, Spring MVC có thể chạy Jakarta validation do `@Valid` trên **argument**. Nếu DTO sai, đường xử lý argument validation thường tạo `MethodArgumentNotValidException` khi không có `BindingResult` xử lý cục bộ.

### Quên `@Valid`

~~~java
@PostMapping("/tickets")
public TicketReply create(
        @RequestBody TicketRequest request) {
    // ...
}
~~~

Khi không có trigger khác yêu cầu method validation, đây là một Java object đã parse nhưng **không tự kiểm tra constraint metadata**. `@RestController`/`@RequestBody` không có nghĩa “tự động validate mọi DTO”.

### `@Validated` có thể thay `@Valid` và chọn groups

~~~java
@PostMapping("/tickets")
public TicketReply create(
        @Validated(Create.class)
        @RequestBody TicketRequest request) {
    // ...
}
~~~

`@Validated(Create.class)` chọn group Create khi binding/validation ở argument tương ứng; cần định nghĩa `Create` và constraint groups đúng. Không tự thay `@Valid` bằng một group tùy chỉnh nếu chưa xác nhận constraints thuộc group đó.

### Đừng chỉ gắn `@Validated` lên DTO class

~~~java
@Validated
public record TicketRequest(
    @NotBlank String title) {
}
~~~

Annotation trên DTO class **không phải** bảo đảm mọi endpoint sử dụng DTO đều validate. Điểm trigger vẫn phải là handler parameter, manual validator hoặc method-validation service proxy tương ứng.

### `BindingResult` làm handler vẫn chạy

~~~java
@PostMapping("/form")
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("ticket") TicketForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }
    return ResponseEntity.ok().build();
}
~~~

Đây là snippet với `TicketForm` đã được khai báo. `BindingResult` cần ở **ngay sau** validated argument. Nếu có errors, controller vẫn có thể được gọi để tự xử lý. Do đó handler được gọi **không có nghĩa validation chưa chạy**; vấn đề có thể là controller **không đọc `errors.hasErrors()`**.

## 6. Direct method constraints khác với `@Valid`

Khi Spring MVC 6.1+ chạy built-in method validation, direct constraint trên method parameter có cơ chế riêng:

~~~java
@GetMapping("/quota")
public Map<String,Integer> quota(
        @RequestParam("count") @Min(1) int count) {
    return Map.of("count", count);
}
~~~

Với `count=0`, type conversion thành công; `@Min(1)` sai và Spring MVC thường dùng `HandlerMethodValidationException`.

Với `count=abc`, chuyển kiểu từ chuỗi sang `int` thất bại; thường là `MethodArgumentTypeMismatchException` **trước** khi `@Min` có thể đánh giá.

| Input | Vấn đề | Exception thường gặp |
|---|---|---|
| JSON `{"title":""}`, `@Valid @RequestBody` | Jakarta constraint | `MethodArgumentNotValidException` |
| `count=0`, `@Min(1) int` | Direct method constraint | `HandlerMethodValidationException` |
| `count=abc`, `int` | Argument conversion | `MethodArgumentTypeMismatchException` |
| Body `{` | JSON parsing | `HttpMessageNotReadableException` |
| Bỏ `@Valid` trên body, không có trigger khác | DTO annotations không được yêu cầu validate | Có thể handler tiếp tục |

**Test chỉ HTTP status 400 chưa đủ để kết luận validation có chạy.** Nên kiểm tra `BindingResult.getFieldErrors()` và exception class khi test chẩn đoán.

### Controller class-level `@Validated`

Tài liệu Spring 6.2 chỉ ra rằng nếu controller có `@Validated` ở **cấp class**, method validation có thể được áp dụng qua **AOP proxy**. Để dùng built-in MVC method validation giới thiệu từ Spring 6.1, nên **bỏ class-level `@Validated` trên controller**.

Quy tắc này **không áp dụng nguyên xi cho service**: service bean thường cần `@Validated` cấp class để kích hoạt AOP method validation.

## 7. Nested object thiếu cascade

DTO:

~~~java
public record Contact(
    @NotBlank String email) {
}

public record TicketRequest(
    @NotBlank String title,
    Contact contact) {
}
~~~

Ngay cả khi controller có `@Valid @RequestBody TicketRequest`, validation của nested `contact.email` **không nhất thiết chạy** nếu property `contact` thiếu cascade `@Valid`.

Sửa:

~~~java
public record TicketRequest(
    @NotBlank String title,
    @NotNull @Valid Contact contact) {
}
~~~

Hai annotation khác vai trò:

- `@NotNull` trên contact: contact không được null.
- `@Valid` trên contact: nếu có object, kiểm tra constraints bên trong Contact.

**`@Valid` tự nó không yêu cầu object phải khác null.** Một nested object null được cascade bỏ qua theo semantics thường gặp. Vì vậy thêm `@NotNull` nếu cần bắt buộc.

Với collections:

~~~java
public record TicketBatch(
    @NotEmpty
    List<@Valid TicketRequest> tickets) {
}
~~~

Cần kiểm tra nested elements và đồng thời giới hạn số phần tử/bộ nhớ. `@Valid` không thay thế `@Size(max=...)` hoặc body byte limits.

## 8. Không phải mọi giá trị đều vi phạm constraint

| Constraint | Null | Blank/empty | Ghi chú |
|---|---|---|---|
| `@NotNull` | Sai | Có thể hợp lệ | Chỉ kiểm tra null |
| `@NotBlank` | Sai | Sai với CharSequence blank | Dành cho chuỗi |
| `@NotEmpty` | Sai | Sai với chuỗi/collection/map/array rỗng | Không đồng nhất với non-whitespace |
| `@Size(min=1)` | Thường hợp lệ | Chuỗi rỗng sai | Kết hợp NotNull nếu null không được phép |
| `@Pattern` | Thường hợp lệ | Tùy regex | Không mặc định bắt buộc nhập |
| `@Min(1)` | Thường hợp lệ | Không áp dụng chuỗi bất kỳ | Kết hợp NotNull nếu cần |
| `@Valid` | Bỏ qua nested null | Không phải direct constraint | Chỉ yêu cầu cascade |

Một test dùng `name=""` để kiểm tra `@NotNull` sẽ không phát violation vì chuỗi rỗng khác null. Ngược lại, dùng `@NotBlank` lên `Integer` là kiểu không hỗ trợ và có thể gây `UnexpectedTypeException`; không phải lỗi “provider không chạy”.

**Mẹo chẩn đoán:** dùng một fixture chắc chắn sai, ví dụ `@NotBlank String title=""`, trước khi mở rộng sang annotation phức tạp, null semantics và custom validators.

## 9. Service method validation và Spring proxy

Một service hợp lệ:

~~~java
@Service
@Validated
public class TicketService {

    public TicketReceipt submit(
            @NotBlank String source,
            @Valid TicketRequest request) {
        // ...
    }
}
~~~

Khi Spring Boot có provider và method validation auto-configuration thích hợp, lời gọi **qua Spring-managed bean proxy** có thể phát `jakarta.validation.ConstraintViolationException` nếu `source=" "` vi phạm `@NotBlank`.

### Gọi bằng `new` không có proxy

~~~java
TicketService service = new TicketService();
service.submit(" ", validRequest);
~~~

Đây chỉ là Java object tự tạo, không có proxy method-validation. Annotation `@NotBlank` không tự chèn mã kiểm tra vào method body.

### Self-invocation

~~~java
public void outer() {
    inner(" "); // Lời gọi nội bộ.
}

public void inner(@NotBlank String input) {
    // ...
}
~~~

Đây là snippet mô tả. Khi dùng proxy-based AOP, `this.inner(...)` thường **bypass interceptor**. Lời gọi từ một bean khác vào proxy mới là đường expected. Tương tự, final/private methods hoặc class cấu hình proxy không phù hợp có thể hạn chế interception.

### Những điều cần xác minh

- Service có `@Service`/`@Component` và nằm trong component scan?
- Có `@Validated` cấp class trên service?
- Method là method được proxy có thể intercept?
- Request/other bean có inject service qua Spring, không dùng `new`?
- Không phải self-invocation?
- Spring MethodValidationPostProcessor/auto-configuration được bật, không bị exclude hoặc override?
- Provider Jakarta tương thích đang hoạt động?

Nếu test `jakartaValidator.validate(dto)` PASS nhưng service proxy test fail, **đừng thêm annotation ngẫu nhiên vào DTO**; hãy kiểm tra đường AOP.

## 10. Validation groups làm một constraint biến mất

Ví dụ:

~~~java
public interface Create {
}

public record GroupedTicket(
    @NotBlank(groups = Create.class)
    String title) {
}
~~~

Khi gọi:

~~~java
validator.validate(request);
~~~

mặc định validate nhóm `Default`. Constraint trên `title` chỉ thuộc `Create` nên không được chọn.

Để kiểm tra:

~~~java
validator.validate(request, Create.class);
~~~

Trong Spring MVC:

~~~java
public void create(
        @Validated(Create.class)
        @RequestBody GroupedTicket request) {
}
~~~

Đây là snippets minh họa, cần imports/definitions khi đưa vào project riêng. Nếu cấu hình group sequence hoặc inheritance, cách tập hợp constraints có thể khác.

**Sai lầm thường gặp:** chuyển handler từ `@Valid` sang `@Validated(SomeGroup.class)` và nghĩ mọi constraint ở nhóm Default vẫn chạy; phải xem khai báo `groups`/`@GroupSequence` cụ thể.

## 11. Custom constraint: kiểm tra metadata và điểm dùng

Một custom constraint yêu cầu annotation có runtime metadata:

~~~java
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = CodeValidator.class)
public @interface ValidCode {
    String message() default "Invalid code";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Đây là snippet, chưa phải file độc lập: cần imports `java.lang.annotation.*`, `jakarta.validation.Constraint`/`Payload` và implementation `CodeValidator`. Provider chỉ có thể chạy khi annotation được định nghĩa/đặt đúng type/target, `validatedBy` trỏ đúng `ConstraintValidator<ValidCode,T>`, group được chọn và có entry point.

Với custom `ConstraintValidator` cần inject Spring dependencies, `LocalValidatorFactoryBean` thường cấu hình `SpringConstraintValidatorFactory`. Tạo một Jakarta `ValidatorFactory` thuần trong unit test **không mặc nhiên autowire dependencies Spring** vào custom validator của bạn. Tách test logic validator khỏi test DI/wiring, hoặc dùng application context khi cần.

Các nguyên nhân thường gặp:

- `@Retention` không phải RUNTIME.
- `@Target` không bao gồm FIELD, METHOD, PARAMETER hay TYPE phù hợp nơi annotation được đặt.
- `@Constraint(validatedBy=...)` bị bỏ hoặc trỏ sai class.
- Import `javax.validation.ConstraintValidator` trong project Jakarta.
- Generic target type của validator không tương thích property type.
- Group không được chọn.
- Annotation đặt trên property khác với object thật được validate.
- Đã tạo annotation đúng nhưng hoàn toàn chưa kích hoạt validation.

Đừng vội thêm log khắp `isValid`; trước hết chạy test provider trực tiếp trên instance sai và inspect `getConstraintsForClass(...)`.

## 12. Spring Validator custom không tự kích hoạt

Ngoài Jakarta Bean Validation còn có:

~~~java
public final class TicketPolicyValidator
        implements org.springframework.validation.Validator {

    @Override
    public boolean supports(Class<?> type) {
        return TicketRequest.class.isAssignableFrom(type);
    }

    @Override
    public void validate(
            Object target,
            org.springframework.validation.Errors errors) {
        // Gọi rejectValue hoặc reject khi cần.
    }
}
~~~

Đây là snippet với `TicketRequest` và imports phù hợp. Chỉ tạo class hoặc gắn `@Component` **không bảo đảm MVC tự gọi** custom Spring Validator này.

Cần đăng ký:

~~~java
@InitBinder("ticketRequest")
void configure(WebDataBinder binder) {
    binder.addValidators(new TicketPolicyValidator());
}
~~~

Đây là snippet trong controller, object name phải khớp. Sau đó validation phải được trigger đúng lúc. Nếu dùng `binder.setValidator(...)` thay vì `addValidators(...)`, có thể thay thế validator khác mà bạn cần giữ.

Manual DataBinder:

~~~java
DataBinder binder = new DataBinder(target, "ticketRequest");
binder.setValidator(customValidator);
binder.bind(propertyValues);
binder.validate();

BindingResult result = binder.getBindingResult();
~~~

Ở đây `bind` chỉ gắn input; **`validate()`** mới yêu cầu validator chạy. Spring `BeanPropertyBindingResult` đơn lẻ chỉ lưu errors, không tự gọi validator.

## 13. Project mẫu Spring Boot 3.5 / Java 17+

Tạo project Spring Initializr với **Spring Web + Validation**; thêm starter test để kiểm thử. Ví dụ này phân biệt provider, MVC argument validation và service method AOP.

Package chung: `com.example.validationdiagnosis`.

### 13.1. Gradle dependencies

Trong project đã có Spring Boot Gradle plugin/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Không thêm riêng `javax.validation-api` vào project này. Code cần Java 17+ và dependency management của Spring Boot 3.5.

### 13.2. `ValidationDiagnosisApplication.java`

`src/main/java/com/example/validationdiagnosis/ValidationDiagnosisApplication.java`:

~~~java
package com.example.validationdiagnosis;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationDiagnosisApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ValidationDiagnosisApplication.class, args);
    }
}
~~~

### 13.3. `CreateTicketRequest.java`

`src/main/java/com/example/validationdiagnosis/CreateTicketRequest.java`:

~~~java
package com.example.validationdiagnosis;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateTicketRequest(
    @NotBlank String title,
    @NotNull @Min(1) Integer quantity,
    @NotNull @Valid Contact contact
) {
    public record Contact(
        @NotBlank String email
    ) {
    }
}
~~~

Nếu `title=""`, root constraint báo lỗi. Nếu `quantity=0`, `Min` báo lỗi. Nếu `contact.email=""`, nested constraint báo lỗi nhờ cascade `@Valid`. Nếu `contact=null`, `@NotNull` báo lỗi mà không yêu cầu provider đi vào object không tồn tại.

### 13.4. `TicketService.java`

`src/main/java/com/example/validationdiagnosis/TicketService.java`:

~~~java
package com.example.validationdiagnosis;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class TicketService {

    public TicketReceipt submit(
            @NotBlank String source,
            @Valid CreateTicketRequest request) {

        return new TicketReceipt(
            "ACCEPTED", request.title());
    }

    public record TicketReceipt(
        String status, String title) {
    }
}
~~~

`@Validated` cấp class yêu cầu service method validation khi được gọi qua Spring proxy. Method được thiết kế **public, non-final** và không tự kiểm tra `source` bằng if, để test thấy khác biệt giữa external-proxy call và direct Java call.

### 13.5. `TicketController.java`

`src/main/java/com/example/validationdiagnosis/TicketController.java`:

~~~java
package com.example.validationdiagnosis;

import java.util.Map;

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

@RestController
@RequestMapping("/api/tickets")
public class TicketController {

    private final TicketService tickets;

    public TicketController(TicketService tickets) {
        this.tickets = tickets;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<TicketService.TicketReceipt> create(
            @Valid @RequestBody CreateTicketRequest request) {

        TicketService.TicketReceipt receipt =
            tickets.submit("web", request);

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(receipt);
    }

    @GetMapping("/quota")
    public Map<String, Integer> quota(
            @RequestParam("count") @Min(1) int count) {
        return Map.of("count", count);
    }
}
~~~

**Không có `@Validated` cấp class trên controller**, nhằm sử dụng built-in MVC method validation của Spring 6.1+. `TicketService` có `@Validated` riêng vì AOP service validation là một boundary khác.

### 13.6. Chạy thử HTTP

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Request đúng:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/tickets" \
  -H "Content-Type: application/json" \
  -d '{"title":"Repair","quantity":2,"contact":{"email":"a@example.org"}}'
~~~

Kỳ vọng HTTP **201 Created** và body:

~~~json
{
  "status": "ACCEPTED",
  "title": "Repair"
}
~~~

Request sai title:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/tickets" \
  -H "Content-Type: application/json" \
  -d '{"title":"","quantity":2,"contact":{"email":"a@example.org"}}'
~~~

Kỳ vọng HTTP **400 Bad Request** do `@NotBlank`. Body lỗi mặc định **không được cố định ở đây** vì Spring Boot config/ProblemDetail/advice có thể khác; test sẽ kiểm tra exception class và field path.

Request nested email sai:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/tickets" \
  -H "Content-Type: application/json" \
  -d '{"title":"Repair","quantity":2,"contact":{"email":""}}'
~~~

Kỳ vọng HTTP 400, `FieldError` có path `contact.email`.

Request direct `@Min`:

~~~bash
curl -i \
  "http://localhost:8080/api/tickets/quota?count=0"
~~~

Kỳ vọng HTTP 400 do `@Min(1)`. Với `count=1`, HTTP 200:

~~~json
{"count":1}
~~~

Nếu gửi `count=abc`, đây là lỗi type conversion chứ không phải `@Min` violation; HTTP 400 không chứng minh direct constraint đã chạy.

## 14. MockMvc tests: kiểm tra validation trigger thực sự

`src/test/java/com/example/validationdiagnosis/TicketValidationMvcTest.java`:

~~~java
package com.example.validationdiagnosis;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TicketValidationMvcTest {

    @Autowired
    private MockMvc mvc;

    private static String json(
            String title, String quantity, String email) {
        return "{\"title\":\"" + title
            + "\",\"quantity\":" + quantity
            + ",\"contact\":{\"email\":\"" + email
            + "\"}}";
    }

    @Test
    void validTicketIsCreated() throws Exception {
        mvc.perform(post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("Repair", "2", "a@example.org")))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.status").value("ACCEPTED"))
            .andExpect(jsonPath("$.title").value("Repair"));
    }

    @Test
    void blankTitleTriggersRequestBodyValidation()
            throws Exception {
        mvc.perform(post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("", "2", "a@example.org")))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                MethodArgumentNotValidException ex =
                    assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("title"));
            });
    }

    @Test
    void zeroQuantityTriggersMin() throws Exception {
        mvc.perform(post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("Repair", "0", "a@example.org")))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                MethodArgumentNotValidException ex =
                    assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("quantity"));
            });
    }

    @Test
    void nestedBlankEmailIsValidated() throws Exception {
        mvc.perform(post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json("Repair", "2", "")))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                MethodArgumentNotValidException ex =
                    assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("contact.email"));
            });
    }

    @Test
    void missingContactIsRejected() throws Exception {
        mvc.perform(post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"title\":\"Repair\",\"quantity\":2,"
                    + "\"contact\":null}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                MethodArgumentNotValidException ex =
                    assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("contact"));
            });
    }

    @Test
    void minOnRequestParamTriggersMethodValidation()
            throws Exception {
        mvc.perform(get("/api/tickets/quota")
                .param("count", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> assertInstanceOf(
                HandlerMethodValidationException.class,
                result.getResolvedException()));
    }

    @Test
    void validCountPasses() throws Exception {
        mvc.perform(get("/api/tickets/quota")
                .param("count", "1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(1));
    }

    @Test
    void conversionFailureIsNotMinViolation()
            throws Exception {
        mvc.perform(get("/api/tickets/quota")
                .param("count", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> assertInstanceOf(
                MethodArgumentTypeMismatchException.class,
                result.getResolvedException()));
    }

    @Test
    void malformedJsonIsNotBeanValidation()
            throws Exception {
        mvc.perform(post("/api/tickets")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Chín tests trên chứng minh boundary MVC: có provider/trigger, nested cascade, direct method constraint và sự khác nhau giữa validation, conversion, JSON parse. `json(...)` helper chỉ ghép synthetic test strings; với dữ liệu chứa quotes/backslashes tùy ý, dùng Jackson `ObjectMapper` thay vì ghép tay.

## 15. Test Jakarta provider và service AOP riêng

### `ProviderDiagnosticsTest.java`

`src/test/java/com/example/validationdiagnosis/ProviderDiagnosticsTest.java`:

~~~java
package com.example.validationdiagnosis;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ProviderDiagnosticsTest {

    @Autowired
    private Validator jakartaValidator;

    @Test
    void providerFindsRootAndNestedViolations() {
        CreateTicketRequest bad = new CreateTicketRequest(
            "", 0,
            new CreateTicketRequest.Contact(""));

        Set<ConstraintViolation<CreateTicketRequest>> violations =
            jakartaValidator.validate(bad);

        Set<String> paths = violations.stream()
            .map(v -> v.getPropertyPath().toString())
            .collect(Collectors.toSet());

        assertTrue(paths.contains("title"));
        assertTrue(paths.contains("quantity"));
        assertTrue(paths.contains("contact.email"));
    }

    @Test
    void providerFindsConstraintMetadata() {
        assertTrue(jakartaValidator
            .getConstraintsForClass(CreateTicketRequest.class)
            .isBeanConstrained());
    }
}
~~~

Nếu hai tests này PASS, provider và metadata cơ bản hoạt động; nếu cùng DTO qua MockMvc lại không sinh lỗi, cần tập trung vào controller trigger/configuration.

### `TicketServiceValidationTest.java`

`src/test/java/com/example/validationdiagnosis/TicketServiceValidationTest.java`:

~~~java
package com.example.validationdiagnosis;

import jakarta.validation.ConstraintViolationException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class TicketServiceValidationTest {

    @Autowired
    private TicketService tickets;

    private static CreateTicketRequest good() {
        return new CreateTicketRequest(
            "Repair", 2,
            new CreateTicketRequest.Contact("a@example.org"));
    }

    @Test
    void springProxyRejectsBadDirectArgument() {
        assertThrows(
            ConstraintViolationException.class,
            () -> tickets.submit(" ", good()));
    }

    @Test
    void springProxyValidatesNestedDto() {
        CreateTicketRequest bad = new CreateTicketRequest(
            "", 2,
            new CreateTicketRequest.Contact("a@example.org"));

        assertThrows(
            ConstraintViolationException.class,
            () -> tickets.submit("web", bad));
    }

    @Test
    void newObjectDoesNotInvokeSpringInterceptor() {
        TicketService direct = new TicketService();

        assertDoesNotThrow(
            () -> direct.submit(" ", good()));
    }
}
~~~

**Tổng 14 test methods**: 9 MockMvc + 2 provider + 3 service. Test cuối chứng minh việc tạo object bằng `new` bypass Spring proxy; đây là quan sát kỹ thuật, **không phải khuyến nghị bỏ qua validation**.

### Cách chạy

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng smoke test provider:

~~~bash
./gradlew test \
  --tests "com.example.validationdiagnosis.ProviderDiagnosticsTest"
~~~

Đây là các tests **được thiết kế để PASS với Spring Boot 3.5 và cấu hình nêu trên**. Bài viết chỉ kiểm tra tĩnh code và tài liệu API; **không tuyên bố đã chạy Gradle**.

Nếu provider test FAIL do context không khởi động được, xem first root cause và dependency graph. Nếu provider PASS nhưng service fail, xem `@Validated`/MethodValidationPostProcessor/proxy. Nếu provider PASS và service PASS nhưng MVC fail, xem `@Valid`/global MVC validator/handler exception resolution.

## 16. Chẩn đoán bằng quyết định if–then

~~~text
A. Jakarta import đúng?
  |-- Không: migrate javax -> jakarta, fix deps
  |-- Có
      |
      v
B. Provider có trong runtimeClasspath?
  |-- Không: starter-validation/provider
  |-- Có
      |
      v
C. jakartaValidator.validate(badFixture) phát lỗi?
  |-- Không:
  |     - Check group/constraint semantics
  |     - Check nested @Valid
  |     - Check custom @Target/@Retention/@Constraint
  |     - Check provider initialization
  |
  |-- Có:
        |
        v
D. Code đang chạy qua boundary nào?
   |-- Spring MVC:
   |     - @Valid/@Validated trên DTO argument?
   |     - Direct method constraint?
   |     - BindingResult ngay sau?
   |     - MVC getValidator() có bị override?
   |
   |-- Service:
   |     - @Validated trên service type?
   |     - Spring bean/proxy?
   |     - Self-invocation/new/final?
   |
   |-- Manual:
         - validator.validate(...) đã gọi?
         - DataBinder.validate() đã gọi?
        |
        v
E. Đã có violation/exception nhưng HTTP vẫn success?
   |-- Read BindingResult.hasErrors()
   |-- Check @ControllerAdvice/catch-all mapping
   |-- Distinguish type mismatch vs validation
~~~

Quy trình này định vị nguyên nhân thay vì thêm/sửa annotations theo cảm giác.

## 17. Có `@Valid` nhưng handler không ném exception: kiểm tra BindingResult

~~~java
@PostMapping("/form")
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("ticket") TicketForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }

    return ResponseEntity.ok().build();
}
~~~

Đây là snippet cần định nghĩa `TicketForm`. Nếu có `BindingResult` **ngay sau argument**, Spring MVC có thể vẫn gọi handler khi form có lỗi. Đừng nhầm “handler chạy” với “constraint không chạy”. Để kiểm tra, xem `errors.getFieldErrors()`/`getGlobalErrors()` và quyết định response.

Một handler bỏ qua errors rồi trả `200 OK` là lỗi của **error-handling policy**, ngay cả khi provider đã phát hiện violations đúng.

Nếu method có direct constraints ở parameters khác, validation của toàn method có thể dùng `HandlerMethodValidationException`. `BindingResult` của một DTO không tự gom các lỗi của mọi parameter khác.

## 18. Custom global MVC Validator vô tình thay thế Jakarta validator

Spring MVC thường tích hợp `LocalValidatorFactoryBean` khi Bean Validation có trên classpath. Nếu ứng dụng override:

~~~java
@Configuration
public class CustomMvcConfig implements WebMvcConfigurer {

    @Override
    public org.springframework.validation.Validator getValidator() {
        return new MyCustomValidator();
    }
}
~~~

Đây là snippet minh họa; `MyCustomValidator` phải được định nghĩa riêng. Nếu global validator custom **không chạy Jakarta Bean Validation**, `@NotBlank`/`@Min` trong MVC có thể không còn được áp dụng như trước.

Thay vì override global validator một cách thiếu kiểm soát:

- Giữ pipeline Jakarta validator mặc định nếu vẫn cần Bean Validation.
- Thêm custom Spring Validator ở scope cụ thể bằng `@InitBinder` và `binder.addValidators(...)` khi phù hợp.
- Nếu cần custom global configuration, đảm bảo adapter/provider vẫn được dùng.
- Viết MockMvc regression test với DTO chắc chắn sai.

Một `OptionalValidatorFactoryBean` có thể xử lý tình huống thiếu provider theo cách **không thực thi validation**; không coi nó là giải pháp bảo đảm constraints chạy. Nếu provider bắt buộc cho an toàn dữ liệu, smoke test nên fail khi provider không hoạt động.

## 19. Vì sao lỗi dường như “không được hiển thị” dù constraint đã chạy?

Có thể validation đã tạo `ConstraintViolation`/`FieldError` nhưng:

- Advice catch-all nuốt exception và trả response mặc định.
- Controller nhận `BindingResult` mà không kiểm tra `hasErrors()`.
- Frontend không đọc error body/schema hiện tại.
- Mã message không có bản dịch tương ứng trong `MessageSource`.
- Một group/field path mới không khớp error mapper.
- Global/object error bị bỏ vì mapper chỉ lấy `getFieldErrors()`.
- Test chỉ nhìn HTTP status mà không xem resolved exception.

### `MessageSource` không quyết định constraint có chạy

`MessageSource` chỉ giải quyết **message codes → câu văn theo locale**. Nó không có nhiệm vụ bootstrap provider, kích hoạt `@Valid` hoặc chạy `ConstraintValidator`. Thiếu bản dịch có thể khiến message trở về default message hoặc lookup thất bại, nhưng đó là vấn đề **hiển thị thông báo**, không phải bằng chứng constraint chưa được đánh giá.

Một `FieldError` có các ứng viên mã (ví dụ `NotBlank.ticket.title`, `NotBlank.title`, `NotBlank.java.lang.String`, `NotBlank`). `MessageSource.getMessage(error,locale)` cố resolve các keys này. Hãy phân biệt **việc ghi lỗi trong `BindingResult`** với **việc hiển thị lỗi** ở response/view.

### Không lộ dữ liệu nhạy cảm

Khi debug, `ConstraintViolation.getInvalidValue()` hoặc `FieldError.getRejectedValue()` có thể chứa password, token hoặc PII. Dùng fixture giả trong test; trong production log codes/counts/route template thay vì log raw input. Không trả stack trace hoặc class/method nội bộ qua API.

## 20. Bảng xử lý sự cố

| Hiện tượng | Nguyên nhân khả dĩ | Cách xác minh |
|---|---|---|
| Provider bootstrap ném `NoProviderFoundException` | Không có provider runtime | Gradle dependencyInsight, packaging |
| Boot 3 nhưng vẫn import `javax.validation` | Sai namespace | Quét imports, migrate Jakarta |
| `@NotBlank` compile nhưng DTO invalid đi qua | Không có trigger MVC | Kiểm tra `@Valid @RequestBody` |
| DTO root valid test PASS, nested sai bỏ qua | Thiếu `@Valid` trên nested property | Test `contact.email` path |
| `@Valid` nested nhưng null vẫn pass | Thiếu `@NotNull` | Thêm constraint null phù hợp |
| `@Size` không reject null | Đây là semantics | Dùng thêm `@NotNull` |
| `@NotNull` không reject `""` | Blank vẫn non-null | Dùng `@NotBlank` |
| `@Validated(Create.class)` bỏ qua rule Default | Nhóm khác nhau | Đối chiếu groups |
| Custom constraint không gọi `isValid` | Metadata/trigger/provider | Kiểm tra @Retention/@Target/@Constraint |
| Service không ném exception | Thiếu @Validated/proxy | Test bean qua Spring |
| Gọi cùng class không validate | Self-invocation | Tách bean boundary |
| Gọi bằng `new` không validate | Bypass Spring AOP | Inject Spring-managed bean |
| Spring Validator tự viết không chạy | Chưa register/`validate()` | @InitBinder/DataBinder test |
| Có HTTP 400 nhưng không thấy `@Min` | Type mismatch/parse error | Xem exception class |
| HTTP 200 dù lỗi nằm trong BindingResult | Controller bỏ qua errors | Assert hasErrors/response |
| Global MVC validator bị thay | Custom getValidator() | Inspect WebMvcConfigurer |
| Service provider PASS nhưng HTTP fail | Boundary khác | MockMvc exception/field tests |
| Đa ngữ sai nhưng constraint có lỗi | MessageSource cấu hình | Test codes và locale |
| Phần mềm cập nhật xong constraint “mất” | BOM/dependency/exclusion thay đổi | Test provider ở đúng artifact |

## 21. Bài tập tự kiểm tra

**1.** Có API `jakarta.validation-api` nhưng không có provider; annotation có tự chạy không? — Không.

**2.** Provider test trực tiếp phát violations nhưng MVC không; kiểm tra trước tiên? — `@Valid`/`@Validated` trên handler argument và MVC validator wiring.

**3.** `@Valid @RequestBody` không thấy lỗi trong nested contact; vì sao? — Thường do nested property thiếu `@Valid` hoặc group/metadata sai.

**4.** Vì sao cần cả `@NotNull` và `@Valid` trên nested contact? — Một cái từ chối null, một cái yêu cầu cascade vào bean có mặt.

**5.** Service `@Validated` nhưng `new Service()` vẫn nhận input sai, vì sao? — Không có Spring proxy/interceptor.

**6.** `this.inner()` trong cùng bean có kích hoạt AOP method validation không? — Thường không, vì self-invocation bypass proxy.

**7.** `@Min(1)` có reject `null` không? — Thường không; dùng `@NotNull` nếu null không hợp lệ.

**8.** `@NotNull` có reject `""` không? — Không; chuỗi rỗng vẫn khác null.

**9.** HTTP 400 khi `count=abc` có chứng minh `@Min` chạy không? — Không; đó có thể là conversion failure.

**10.** `@Validated(Create.class)` có bỏ qua Default constraints không? — Có thể, tùy group membership/group sequence.

**11.** Dùng `MessageSource` có tự kích hoạt `@Valid` không? — Không; nó chỉ giải quyết thông báo từ mã lỗi.

**12.** Test nào giúp phân biệt provider với Spring MVC wiring? — Test Jakarta validator trực tiếp rồi MockMvc với cùng invalid DTO.

**13.** Handler nhận `BindingResult` rồi trả success không kiểm tra errors: provider có chắc chết? — Không; lỗi có thể đã được ghi nhưng handler bỏ qua.

**14.** Vì sao test proxy service phải inject bean từ Spring? — Để chạy qua MethodValidationPostProcessor/AOP interception.

## 22. Checklist triển khai và QA

- [ ] Có `spring-boot-starter-validation` trong runtime module cần validate.
- [ ] Dùng đúng `jakarta.validation.*` với Spring Boot 3.
- [ ] Direct provider test với fixture chắc chắn sai.
- [ ] Không dùng một HTTP 400 bất kỳ làm bằng chứng constraint chạy.
- [ ] Đặt `@Valid`/`@Validated` đúng trên MVC argument.
- [ ] Nested object có `@Valid`; thêm `@NotNull` nếu bắt buộc.
- [ ] Direct constraints dùng đúng đường MVC method validation.
- [ ] Không đặt `@Validated` cấp controller khi cần built-in MVC method validation.
- [ ] Service có `@Validated` cấp type và được gọi qua Spring proxy.
- [ ] Cẩn thận `new`, self-invocation, final/private methods.
- [ ] Kiểm tra Default/custom groups và group sequence.
- [ ] Rà metadata custom constraints: target, retention, validatedBy.
- [ ] Spring Validator custom phải được đăng ký/called.
- [ ] Manual DataBinder phải gọi `binder.validate()`.
- [ ] Không thay global MVC validator bằng no-op.
- [ ] Handler có BindingResult phải kiểm tra `hasErrors()`.
- [ ] Xử lý `MethodArgumentNotValidException`, `HandlerMethodValidationException` và conversion errors phù hợp.
- [ ] Dùng `MessageSource` đúng mục đích để dịch errors.
- [ ] Không log hoặc trả rejected values nhạy cảm.
- [ ] Có provider, MVC và service-proxy integration tests.
- [ ] Kiểm tra runtimeClasspath, build artifact và CI sau upgrade.
- [ ] Chạy `./gradlew test` trước khi khẳng định tests đã thực thi thành công.

**Kết luận:** Khi constraint không chạy, đừng chỉ nhìn annotation. Hãy xác minh **API đúng → provider tương thích → validation entry point → groups/cascade → kết quả/exception → HTTP response**. Với Spring MVC, kiểm tra `@Valid`/`@Validated` trên tham số; với service, kiểm tra `@Validated` cấp class và lời gọi qua Spring AOP proxy; với manual code, phải gọi `validate(...)`. **Provider direct test + MockMvc test + service proxy test** là bộ ba giúp định vị nguồn lỗi nhanh nhất.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Framework 6.2 — Java Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — Spring MVC Validator Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — Spring Validator Interface](https://docs.spring.io/spring-framework/reference/6.2/core/validation/validator.html)
- [Spring Framework 6.2 — MethodValidationPostProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html)
- [Spring Framework 6.2 — LocalValidatorFactoryBean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Jakarta Bean Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/)
- [Hibernate Validator — Documentation](https://hibernate.org/validator/documentation/)

# Kiểm thử constructor binding với record và dữ liệu không đầy đủ trong Spring Framework

## 1. Bài toán: request thiếu tham số nhưng record không có setter

Từ Java 16, `record` là kiểu phù hợp để mô tả dữ liệu bất biến theo cấu trúc. Trong Spring MVC 6.1+, `@ModelAttribute` có thể dùng **constructor binding**: Spring đọc các tham số HTTP, chuyển kiểu và truyền chúng vào constructor của đối tượng (ví dụ canonical constructor của record) thay vì cần một no-argument constructor cùng các setter.

Giả sử form đăng ký được mô hình hóa bằng:

```java
public record SignupForm(
        @NotBlank String displayName,
        @NotNull @Min(18) Integer age,
        @Email String email,
        String referralCode
) {}
```

Client có thể gửi đầy đủ:

```http
POST /signup
Content-Type: application/x-www-form-urlencoded

displayName=Lan&age=22&email=lan%40example.org&referralCode=HELLO
```

Hoặc gửi **dữ liệu không đầy đủ**:

```http
POST /signup
Content-Type: application/x-www-form-urlencoded

email=lan%40example.org
```

Câu hỏi kiểm thử không chỉ là “record có được tạo không?” mà còn là:

1. Khi thiếu `displayName` và `age`, Spring lấy giá trị gì để xây constructor?
2. Quy tắc nào báo lỗi “bắt buộc”: constructor binding, `@NotBlank`, `@NotNull` hay `setRequiredFields`?
3. Nếu một tham số có mặt nhưng **không chuyển kiểu được**, ví dụ `age=abc`, lỗi được ghi ở đâu?
4. Vì sao `@Valid @ModelAttribute` có `BindingResult` khác với phương thức không có `BindingResult`?
5. Vì sao cùng một record dạng JSON qua `@RequestBody` không nhất thiết dùng đường binding giống form?
6. Làm sao viết `MockMvc` test đủ: dữ liệu đầy đủ, thiếu trường, giá trị rỗng, sai kiểu, tên tham số được đổi bởi `@BindParam` và tham số thừa?

**Nguyên tắc chính:** constructor binding và Bean Validation là hai giai đoạn **khác nhau**. Spring có thể gán `null` cho thành phần reference type bị thiếu, còn validation constraint như `@NotNull` và `@NotBlank` quyết định trường hợp đó là lỗi. Record bất biến **không tự yêu cầu tất cả thành phần phải hiện diện**.

Phạm vi bài: **Java 17+, Spring Boot 3.3.6, Spring Framework 6.1.x, Servlet Spring MVC và Jakarta Validation**. Với Spring Boot 4 / Spring Framework 7 hoặc cấu hình binder/provider khác, hãy chạy lại bộ test thay vì suy đoán hành vi giống từng chi tiết.

## 2. Từ request form đến constructor của record

### 2.1. @ModelAttribute có cơ chế tìm instance và binding riêng

Với một handler:

```java
@PostMapping("/form")
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult errors) {
    // ...
}
```

Spring MVC tìm/tạo model attribute; khi cần tạo từ HTTP request, nó có thể gọi **primary constructor**, tra các giá trị theo tên tham số và chuyển kiểu chúng. Record có canonical constructor gắn với các record components; không cần constructor không tham số và cũng không cần setter.

Luồng khái niệm:

```text
Request parameters:
  displayName=Lan
  age=22
  email=lan@example.org
        |
        v
Spring MVC @ModelAttribute argument resolver
        |
        v
WebDataBinder / constructor binding
  String "Lan"  -> String displayName
  String "22"   -> Integer age
  String email  -> String email
  missing referralCode -> null
        |
        v
new SignupForm("Lan", 22, "lan@example.org", null)
        |
        v
@Valid -> Jakarta Bean Validation constraints
        |
        v
BindingResult:
  empty -> controller returns success
  errors -> controller/advice returns HTTP 400
```

Hình trên minh họa trường hợp đơn giản với các reference types và constructor không tự từ chối `null`. Nếu tự viết compact constructor có logic ném exception hoặc có nested/collection conversion phức tạp, lỗi tạo đối tượng có thể xuất hiện **trước khi** constraint validation được chạy.

### 2.2. Bảng điều kiện dữ liệu không đầy đủ

Với các constraint đang dùng:

| Tham số | Kiểu thành phần | Khi vắng mặt | Validation |
| --- | --- | --- | --- |
| `displayName` | `String` | Có thể được truyền `null` vào constructor | `@NotBlank` không chấp nhận `null` hoặc chỉ khoảng trắng |
| `age` | `Integer` | Có thể là `null` | `@NotNull` báo thiếu; `@Min(18)` **không** tự cấm null |
| `email` | `String` | Có thể là `null` | `@Email` thông thường cho phép null, nên đây là trường tùy chọn |
| `referralCode` | `String` | Có thể là `null` | Không có constraint bắt buộc |
| `age=abc` | `Integer` | Có **giá trị** nhưng không chuyển được | Binding/conversion error, thường có code `typeMismatch` |

**Không nên dùng “record không cho null” làm giả định.** Bất biến của record nghĩa là không có setter thay đổi component sau khi tạo; nó **không tự thực hiện null checking**.

### 2.3. Kiểm tra giá trị “không có” và giá trị “không hợp lệ” khác nhau

Cần test ít nhất bốn tình huống:

- Tham số **không được gửi**: thiếu key `age`.
- Tham số có key nhưng **rỗng**: `age=`.
- Có giá trị nhưng **sai định dạng**: `age=abc`.
- Có giá trị chuyển kiểu được nhưng **không hợp lệ**: `age=16`.

Chúng có thể dẫn tới các lỗi khác nhau: `NotNull`, `typeMismatch` hoặc `Min`. Với `String`, `displayName=` và `displayName=%20%20` đều không đạt `@NotBlank`; một tham số bị thiếu có thể cũng không đạt `@NotBlank` khi giá trị constructor nhận là null.

Các kết quả phụ thuộc conversion service và cấu hình binding; hãy assert những thuộc tính **có chủ đích** của error response thay vì mã hóa ngầm assumption về reflection/provider.

## 3. @ModelAttribute constructor binding và @RequestBody JSON là hai cơ chế

Một nhầm lẫn phổ biến là dùng từ “constructor binding” để nói chung mọi cách tạo record. Cả hai đường đều có thể cuối cùng gọi canonical constructor, nhưng **thành phần tạo và quy tắc chuyển đổi không giống nhau**.

| | `@ModelAttribute` | `@RequestBody` |
| --- | --- | --- |
| Nguồn dữ liệu phổ biến | Query/form parameters, path variables và headers trong phạm vi MVC resolver | HTTP body được `HttpMessageConverter` đọc (thường Jackson cho JSON) |
| Cơ chế | Spring `WebDataBinder` và primary constructor binding | JSON deserialization qua Jackson |
| Tên tham số | Tên constructor parameter, có thể tùy biến bằng Spring `@BindParam` | JSON property names, Jackson annotations/configuration |
| Chuyển kiểu | Spring conversion service, property editors/formatters | Jackson deserializers |
| Conversion failure | Binding errors hoặc exception tùy giai đoạn | Thường `HttpMessageNotReadableException` |
| Bean Validation | `@Valid` / `@Validated` sau binding | `@Valid` / `@Validated` sau deserialization |
| Thiếu body hoàn toàn | Không phải khái niệm bắt buộc của form parameters | `@RequestBody(required=true)` có thể báo body không đọc được |
| Lỗi validation thông thường | `BindingResult` hoặc `MethodArgumentNotValidException` | `MethodArgumentNotValidException` khi object đã deserialize thành công |

**Quan trọng:** `@BindParam("display-name")` là một quy tắc tên của Spring constructor binding; nó không tương đương Jackson `@JsonProperty("display-name")`. Bài runnable tách hai request DTO để làm nổi bật ranh giới này.

### 3.1. Dữ liệu JSON không đầy đủ

Với:

```java
public record JsonSignup(
        @NotBlank String displayName,
        @NotNull Integer age
) {}
```

và JSON:

```json
{"displayName":"Lan"}
```

trong thiết lập Jackson thông thường của Spring Boot, record có thể được tạo với `age=null`, rồi `@Valid` phát hiện `@NotNull`. Tuy nhiên nếu dự án bật Jackson features yêu cầu creator properties có mặt, hoặc viết constructor tự ném exception khi null, request có thể bị từ chối ở **deserialization** trước validation.

Vì thế test cần kiểm tra cả:

- Thiếu một JSON property.
- Property xuất hiện với JSON `null`.
- Body trống hoặc JSON không parse được.
- JSON đủ properties và types hợp lệ.

Không suy rằng mọi sự thiếu dữ liệu trong JSON đều thành `NotNull`; đường parse phải thành công thì Bean Validation mới xử lý object.

## 4. Ba cơ chế kiểm soát “required” không được nhầm nhau

### 4.1. Bean Validation trên record component

Ví dụ:

```java
public record SignupForm(
        @NotBlank String displayName,
        @NotNull @Min(18) Integer age
) {}
```

- `@NotBlank` nhận diện `null`, chuỗi rỗng hoặc chỉ có whitespace.
- `@NotNull` yêu cầu reference khác null.
- `@Min(18)` kiểm tra giá trị khi không null. `@Min` coi `null` hợp lệ theo Jakarta Validation.
- `@Email` kiểm tra định dạng email khi có giá trị; không tự biến email thành trường bắt buộc.

Nếu thiếu `age`, mong đợi `NotNull` hơn là `Min`. Nếu `age=16`, mong đợi `Min`. Nếu `age=abc`, lỗi là conversion và có thể chưa có đối tượng với `Integer` hợp lệ để `@Min` đánh giá.

### 4.2. @RequestParam(required=true) không áp dụng tự động cho record component

`@RequestParam(required=true)` gắn trực tiếp cho **controller method argument**:

```java
@GetMapping("/simple")
public String simple(@RequestParam String name) {
    return name;
}
```

Nó không tự phát sinh chỉ vì một component của record được đặt tên `name`. Record được bind bằng `@ModelAttribute` có semantics riêng. Đừng dùng ví dụ `@RequestParam` để suy ra mọi constructor parameter thiếu sẽ ném `MissingServletRequestParameterException`.

### 4.3. DataBinder#setRequiredFields không phải chính sách constructor binding

`DataBinder#setRequiredFields("age")` được thiết kế cho property binding qua `bind(PropertyValues)`; Javadoc Spring Framework 6.1 nêu rõ nó **không áp dụng** cho constructor binding qua `construct(ValueResolver)`.

Không nên viết:

```java
@InitBinder("signupForm")
void requireFields(WebDataBinder binder) {
    binder.setRequiredFields("displayName", "age");
}
```

rồi kết luận rằng thiếu tham số canonical constructor chắc chắn tạo error code `required`. Trên đường constructor binding, hãy dùng Bean Validation như `@NotBlank`/`@NotNull` và test đúng behavior. Đoạn trên là **snippet phản ví dụ**, không nằm trong demo runnable.

## 5. @BindParam đổi tên nguồn input cho constructor

HTTP clients có thể gửi tên tham số dùng dấu gạch nối:

```text
display-name=Lan&age=22
```

Trong Java, record component thường dùng camelCase:

```java
public record FormSignup(
        @BindParam("display-name") @NotBlank String displayName,
        @NotNull Integer age
) {}
```

`@BindParam` thuộc:

```java
org.springframework.web.bind.annotation.BindParam
```

Nó được Spring Framework 6.1 hỗ trợ cho constructor parameter/field dùng trong `@ModelAttribute` binding. Với Java record, annotation có target phù hợp có thể được compiler truyền tới canonical constructor parameter hoặc backing field. Test trong bài xác minh `display-name` được nhận còn `displayName` không thay thế alias trong đường constructor đã cấu hình.

Các điểm cần chú ý:

- `@BindParam` **không phải** `@JsonProperty`. Trong endpoint `@RequestBody`, nếu muốn đổi tên JSON, hãy dùng Jackson annotation/configuration phù hợp.
- Đừng nhầm tên HTTP `display-name` với field path trong `BindingResult`: lỗi vẫn có thể được gắn với Java property `displayName`.
- Khi sử dụng `@BindParam` trên record component với nhiều công cụ reflection/AOT, test integration thay vì chỉ test constructor bằng `new`.
- Nếu client gửi cả alias và tên Java, phải xác định chính sách ưu tiên/không chấp nhận trùng thay vì đoán parser sẽ chọn giá trị nào.

## 6. Tại sao record phù hợp cho an toàn data binding?

Một mutable entity có thể có setter cho cả `isAdmin`, `balance` hay `ownerId`. Nếu trực tiếp bind request parameters vào entity ấy, attacker có thể thử gửi thêm các field ngoài ý định nghiệp vụ.

Record form DTO:

```java
public record FormSignup(
        String displayName,
        Integer age,
        String email,
        String referralCode
) {}
```

chỉ có các constructor parameters đã khai báo; nó không có setter cho `isAdmin` hoặc `ownerId`. Đây là một lợi thế của **constructor binding với immutable DTO**.

Để làm rõ chính sách chỉ bind những input được khai báo, Spring MVC 6.1+ hỗ trợ:

```java
@InitBinder("signupForm")
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

`setDeclarativeBinding(true)` cho phép constructor binding, và chỉ cho property binding nếu có `allowedFields` phù hợp. Trong ví dụ runnable, không có mutable setters; flag vẫn giúp mô tả chính sách binder một cách tường minh.

**Cảnh báo:** không phải mọi record tự động an toàn tuyệt đối. Nếu record có component `role` hoặc `ownerId` và controller tự tin lấy giá trị đó để ủy quyền, attacker vẫn có thể gửi chúng. Thiết kế **input DTO chỉ gồm các trường client được phép điều khiển**, lấy identity/role từ server-side security context, validate nghiệp vụ và authorization riêng.

Nếu buộc phải property-bind mutable objects, dùng `setAllowedFields(...)` với danh sách field được phép, không dựa vào blacklist. Nhưng `allowedFields` chủ yếu điều khiển property binding, không thay thế việc thiết kế constructor parameter list đúng đắn.

## 7. Dự án runnable: Spring Boot 3.3.6 + Java 17

Dự án đầy đủ gồm hai đường:

- `POST /api/signup/form/checked`: form-urlencoded, Spring MVC constructor binding record, `@Valid`, `BindingResult` liền kề, controller tự dựng lỗi.
- `POST /api/signup/form/strict`: form-urlencoded, record constructor binding nhưng **không** có `BindingResult`, lỗi được xử lý qua `@RestControllerAdvice`.
- `POST /api/signup/json`: JSON được Jackson deserialize thành record khác, sau đó `@Valid`, cho phép so sánh thiếu property với form.
- `MockMvc` tests bao phủ full, incomplete, optional, blank, below-minimum, type-mismatch, alias, extra parameter, JSON thiếu/null/malformed và error mapping.

### 7.1. Cấu trúc project

```text
record-binding-tests/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/recordbinding/
        RecordBindingApplication.java
        FormSignup.java
        JsonSignup.java
        SignupView.java
        FieldIssue.java
        ApiError.java
        ErrorMapper.java
        SignupController.java
        SignupExceptionAdvice.java
      resources/
        application.properties
    test/
      java/com/example/recordbinding/
        SignupBindingTest.java
```

### 7.2. Gradle

Tệp `settings.gradle`:

```groovy
rootProject.name = 'record-binding-tests'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Flag `-parameters` làm tên tham số Java có mặt trong bytecode runtime cho những nơi Spring dùng reflection/`ParameterNameDiscoverer`. Với Java records, canonical constructor và component metadata giúp Spring xác định names; dù vậy giữ `-parameters` là cấu hình đáng tin cậy khi dự án có cả các lớp constructor-bound thông thường.

`spring-boot-starter-validation` cần thiết để `@Valid` có Jakarta Validation provider. Spring Boot 3 sử dụng `jakarta.validation.*`, không trộn `javax.validation.*` từ các ví dụ cũ.

### 7.3. Main class

Tệp `src/main/java/com/example/recordbinding/RecordBindingApplication.java`:

```java
package com.example.recordbinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RecordBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RecordBindingApplication.class, args);
    }
}
```

Tệp `src/main/resources/application.properties`:

```properties
spring.application.name=record-binding-tests
spring.mvc.problemdetails.enabled=false
```

Dòng `spring.mvc.problemdetails.enabled=false` giữ ví dụ tập trung vào payload tùy chỉnh. Nếu ứng dụng thật đã tiêu chuẩn hóa `ProblemDetail` hoặc `ResponseEntityExceptionHandler`, cần tránh khai báo trùng handler cho cùng exception.

### 7.4. FormSignup: record dùng constructor binding và alias

Tệp `src/main/java/com/example/recordbinding/FormSignup.java`:

```java
package com.example.recordbinding;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.web.bind.annotation.BindParam;

public record FormSignup(
        @BindParam("display-name")
        @NotBlank
        String displayName,

        @NotNull
        @Min(18)
        Integer age,

        @Email
        String email,

        String referralCode
) {}
```

Thành phần:

- `displayName` là tên Java; input form dùng `display-name`.
- `age` là `Integer` thay vì `int` để thể hiện giá trị **không được gửi** bằng null một cách rõ ràng.
- `email` và `referralCode` tùy chọn; có thể được tạo với null.
- Không viết compact constructor ném exception khi null; thiếu field được báo qua `@Valid` và `BindingResult`, không bị phá vỡ ngay ở giai đoạn xây object.

### 7.5. JsonSignup: record riêng cho JSON

Tệp `src/main/java/com/example/recordbinding/JsonSignup.java`:

```java
package com.example.recordbinding;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record JsonSignup(
        @NotBlank String displayName,
        @NotNull @Min(18) Integer age,
        @Email String email
) {}
```

Record này dùng Jackson JSON property `displayName`, không dùng `@BindParam`. Cùng quy tắc Bean Validation nhưng **đường tạo object trước đó khác**.

### 7.6. DTO phản hồi thành công

Tệp `src/main/java/com/example/recordbinding/SignupView.java`:

```java
package com.example.recordbinding;

public record SignupView(
        String displayName,
        Integer age,
        String email,
        String referralCode
) {}
```

Dùng record response giúp Jackson xuất JSON mà không cần trả domain entity. Các trường tùy chọn null vẫn hợp lệ trong ví dụ; ứng dụng production có thể cấu hình serialization policy riêng.

### 7.7. DTO phản hồi lỗi

Tệp `src/main/java/com/example/recordbinding/FieldIssue.java`:

```java
package com.example.recordbinding;

public record FieldIssue(
        String field,
        String code
) {}
```

Tệp `src/main/java/com/example/recordbinding/ApiError.java`:

```java
package com.example.recordbinding;

import java.util.List;

public record ApiError(
        String code,
        List<FieldIssue> errors
) {}
```

Payload cố ý **không trả rejectedValue** hoặc exception stacktrace. Trong bài kiểm thử constructor binding, điều quan trọng nhất là phân biệt **field** và **loại lỗi**. Nếu cần message đa ngữ, bổ sung `MessageSource#getMessage(FieldError,Locale)` và default-message policy riêng; đừng dùng text từ provider làm logic client.

### 7.8. ErrorMapper: chung cho controller và advice

Tệp `src/main/java/com/example/recordbinding/ErrorMapper.java`:

```java
package com.example.recordbinding;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

final class ErrorMapper {

    private ErrorMapper() {}

    static ApiError invalid(BindingResult result) {
        List<FieldIssue> errors = result.getAllErrors()
                .stream()
                .map(ErrorMapper::toIssue)
                .sorted(
                        Comparator.comparing(FieldIssue::field)
                                .thenComparing(FieldIssue::code)
                )
                .toList();

        return new ApiError("VALIDATION_ERROR", errors);
    }

    private static FieldIssue toIssue(ObjectError error) {
        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "";

        String code = Objects.toString(
                error.getCode(), "invalid"
        );

        return new FieldIssue(field, code);
    }
}
```

`BindingResult#getAllErrors()` lấy cả `FieldError` và `ObjectError` (ví dụ constraint cấp lớp). Sort theo `field` rồi `code` để HTTP error array có thứ tự do ứng dụng định nghĩa, không phụ thuộc thứ tự Jakarta Validator hoặc binder. `field=""` là quy ước demo cho lỗi cấp object.

### 7.9. Controller với ba endpoint

Tệp `src/main/java/com/example/recordbinding/SignupController.java`:

```java
package com.example.recordbinding;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/signup")
public class SignupController {

    @InitBinder("signupForm")
    void initSignupBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    @PostMapping(
            path = "/form/checked",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> checked(
            @Valid @ModelAttribute("signupForm") FormSignup input,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body(
                    ErrorMapper.invalid(errors)
            );
        }

        return ResponseEntity.ok(new SignupView(
                input.displayName(),
                input.age(),
                input.email(),
                input.referralCode()
        ));
    }

    @PostMapping(
            path = "/form/strict",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public SignupView strict(
            @Valid @ModelAttribute("signupForm") FormSignup input) {

        // Nếu không hợp lệ, Spring MVC xử lý exception
        // trước khi chạy body của phương thức này.
        return new SignupView(
                input.displayName(),
                input.age(),
                input.email(),
                input.referralCode()
        );
    }

    @PostMapping(
            path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public SignupView json(
            @Valid @RequestBody JsonSignup input) {

        return new SignupView(
                input.displayName(),
                input.age(),
                input.email(),
                null
        );
    }
}
```

**Hai điểm then chốt:**

1. `BindingResult errors` đứng **ngay sau** `@Valid @ModelAttribute(...) FormSignup input`. Spring có thể chuyển errors vào controller để controller tự quyết định HTTP response.
2. `/form/strict` không có `BindingResult` nên khi validation thất bại Spring MVC thường ném `MethodArgumentNotValidException`, được advice xử lý.

Ở `/json`, dữ liệu được Jackson xử lý; `@InitBinder("signupForm")` chỉ áp dụng cho binder của attribute tên `signupForm`, không biến JSON deserialization thành `WebDataBinder.construct`.

### 7.10. Global advice cho strict/form và JSON

Tệp `src/main/java/com/example/recordbinding/SignupExceptionAdvice.java`:

```java
package com.example.recordbinding;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class SignupExceptionAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalid(
            MethodArgumentNotValidException exception) {

        return ResponseEntity.badRequest().body(
                ErrorMapper.invalid(exception.getBindingResult())
        );
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest().body(
                new ApiError("INVALID_JSON", List.of())
        );
    }
}
```

`MethodArgumentNotValidException` phù hợp cho `@Valid` khi object đã bind/deserialize và có violation ở đường argument validation MVC thông thường. `HttpMessageNotReadableException` biểu diễn việc request body JSON không đọc được, chẳng hạn JSON bị cắt giữa chừng. Các exception do constructor tự ném hoặc method validation trực tiếp có thể đi theo loại khác; chúng **không mặc nhiên** rơi vào hai handler trên.

## 8. MockMvc: bộ kiểm thử đầy đủ cho record thiếu dữ liệu

Tệp `src/test/java/com/example/recordbinding/SignupBindingTest.java`:

```java
package com.example.recordbinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupBindingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void completeFormBindsToRecordConstructor() throws Exception {
        mvc.perform(post("/api/signup/form/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("display-name", "Lan")
                .param("age", "22")
                .param("email", "lan@example.org")
                .param("referralCode", "HELLO"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.age").value(22))
            .andExpect(jsonPath("$.email").value("lan@example.org"))
            .andExpect(jsonPath("$.referralCode").value("HELLO"));
    }

    @Test
    void missingRequiredFieldsProduceTwoValidationErrors()
            throws Exception {

        mvc.perform(post("/api/signup/form/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "lan@example.org"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors.length()").value(2))
            .andExpect(jsonPath("$.errors[0].field").value("age"))
            .andExpect(jsonPath("$.errors[0].code").value("NotNull"))
            .andExpect(jsonPath("$.errors[1].field")
                    .value("displayName"))
            .andExpect(jsonPath("$.errors[1].code")
                    .value("NotBlank"));
    }

    @Test
    void missingOptionalFieldsDoNotFailValidation()
            throws Exception {

        mvc.perform(post("/api/signup/form/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("display-name", "Lan")
                .param("age", "22"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.age").value(22));
    }

    @Test
    void blankNameAndTooYoungAgeAreNotMissingFields()
            throws Exception {

        mvc.perform(post("/api/signup/form/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("display-name", "  ")
                .param("age", "16"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors.length()").value(2))
            .andExpect(jsonPath("$.errors[0].field").value("age"))
            .andExpect(jsonPath("$.errors[0].code").value("Min"))
            .andExpect(jsonPath("$.errors[1].field")
                    .value("displayName"))
            .andExpect(jsonPath("$.errors[1].code")
                    .value("NotBlank"));
    }

    @Test
    void invalidNumericFormFieldIsABindingFailure()
            throws Exception {

        mvc.perform(post("/api/signup/form/strict")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("display-name", "Lan")
                .param("age", "not-a-number"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    @Test
    void aliasIsNotTheSameAsJavaComponentName()
            throws Exception {

        mvc.perform(post("/api/signup/form/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("displayName", "Lan")
                .param("age", "22"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors.length()").value(1))
            .andExpect(jsonPath("$.errors[0].field")
                    .value("displayName"))
            .andExpect(jsonPath("$.errors[0].code")
                    .value("NotBlank"));
    }

    @Test
    void extraFieldCannotMutateNonExistentRecordProperty()
            throws Exception {

        mvc.perform(post("/api/signup/form/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("display-name", "Lan")
                .param("age", "22")
                .param("isAdmin", "true"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.isAdmin").doesNotExist());
    }

    @Test
    void missingFormFieldsWithoutBindingResultReachAdvice()
            throws Exception {

        mvc.perform(post("/api/signup/form/strict")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors.length()").value(2));
    }

    @Test
    void jsonMissingRecordPropertiesCanBeValidationErrors()
            throws Exception {

        mvc.perform(post("/api/signup/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"email":"lan@example.org"}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors.length()").value(2));
    }

    @Test
    void explicitJsonNullIsRejectedByNotNull()
            throws Exception {

        mvc.perform(post("/api/signup/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"displayName":"Lan","age":null}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field").value("age"))
            .andExpect(jsonPath("$.errors[0].code").value("NotNull"));
    }

    @Test
    void malformedJsonHasDifferentErrorCode()
            throws Exception {

        mvc.perform(post("/api/signup/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Lan\",\"age\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void validJsonDoesNotUseFormBindParamAlias()
            throws Exception {

        mvc.perform(post("/api/signup/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"displayName":"Lan","age":25}
                        """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").value("Lan"))
            .andExpect(jsonPath("$.age").value(25));
    }
}
```

Có **12 test methods** được chia theo nhóm:

- **Form đủ dữ liệu:** xác nhận `@BindParam("display-name")` và chuyển `age="22"` thành `Integer 22`.
- **Form thiếu bắt buộc:** xác nhận `@NotBlank` và `@NotNull` hoạt động sau constructor binding.
- **Form thiếu optional:** xác nhận không tự phát sinh lỗi vì thiếu `email`/`referralCode`.
- **Blank và giá trị thấp:** phân biệt `NotBlank`/`Min` với “tham số vắng mặt”.
- **Chuyển kiểu sai:** xác nhận request bị từ chối thay vì tiếp tục xử lý record không hợp lệ.
- **Tên alias:** kiểm thử `display-name` so với `displayName`.
- **Dữ liệu thừa:** thử `isAdmin` và xác nhận không có field tương ứng trong public response.
- **Không có BindingResult:** xác nhận global advice có thể xử lý lỗi.
- **JSON thiếu/null/sai cú pháp:** phân biệt Jakarta validation với Jackson parsing.
- **JSON hợp lệ:** chứng minh Jackson dùng tên property riêng, không lấy alias từ `@BindParam` của form record.

### 8.1. Chạy test

Từ thư mục project có Gradle wrapper:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu chưa tạo Gradle wrapper, dùng Gradle đã cài đặt để tạo wrapper, hoặc chạy:

```bash
gradle test
```

**Kỳ vọng:** 12 test PASS trong môi trường phù hợp với Spring Boot 3.3.6/Java 17 và classpath đã khai báo. Các expected results là kết quả thiết kế của bộ kiểm thử; **không khẳng định chúng đã thực sự được chạy** trong quá trình biên soạn bài học. Để xác nhận behavior chính xác trên version của ứng dụng, hãy chạy chúng trong CI.

### 8.2. Không phụ thuộc thứ tự do provider đưa ra

`ErrorMapper` cố ý sort theo `field` rồi `code`. Vì vậy test có thể assert:

```text
age        -> NotNull
displayName -> NotBlank
```

Không nên lấy `BindingResult#getFieldErrors().get(0)` để suy ra field nào luôn có lỗi trước. Bean Validation/provider không cam kết thứ tự đánh giá. Nếu response muốn ưu tiên theo thứ tự form UI thay vì alphabet, hãy định nghĩa comparator riêng và kiểm thử nó.

### 8.3. Vì sao test thiếu optional quan trọng?

Chỉ test request thiếu field bắt buộc có thể tạo ấn tượng “record constructor yêu cầu mọi argument”. Test `missingOptionalFieldsDoNotFailValidation` phủ nhận điều đó: **reference type bị thiếu và không có constraint bắt buộc** có thể hợp lệ.

Ngược lại, nếu business contract yêu cầu email, hãy bổ sung `@NotBlank` (và `@Email`) và đổi expected result. Không thêm test “email missing phải lỗi” trong khi code chỉ dùng `@Email`, vì như vậy test sai với Jakarta Validation.

## 9. Test ma trận các trường hợp thiếu dữ liệu

Một ma trận hữu ích cho code review:

| Trường hợp | Ví dụ | Điều cần kiểm tra | Kết quả với demo |
| --- | --- | --- | --- |
| Đủ trường bắt buộc | `display-name=Lan&age=22` | Bind constructor + validation | HTTP 200 |
| Thiếu tên và tuổi | `email=lan@example.org` | Cả hai constraint | HTTP 400, `NotBlank` và `NotNull` |
| Thiếu optional | Không có `email`, `referralCode` | Optional không gây lỗi | HTTP 200 |
| Tên toàn khoảng trắng | `display-name=%20%20` | `@NotBlank` | HTTP 400 |
| Tuổi dưới giới hạn | `age=16` | `@Min(18)` | HTTP 400 |
| Tuổi không chuyển được | `age=abc` | Conversion/binding | HTTP 400 |
| Đúng tên Java nhưng sai alias | `displayName=Lan` | `@BindParam` | HTTP 400 nếu thiếu `display-name` |
| Có input thừa | `isAdmin=true` | Record không bị mass assignment | Không tạo `isAdmin` |
| JSON thiếu property | `{"age":22}` | Jackson tạo record + Bean Validation | Tùy các field còn thiếu |
| JSON `null` rõ ràng | `{"displayName":"Lan","age":null}` | `@NotNull` | HTTP 400 |
| JSON bị hỏng | `{"age":` | Jackson parsing | HTTP 400, `INVALID_JSON` |
| No request body | POST JSON không body | `@RequestBody(required=true)` | HTTP 400 / unreadable body |

Cần test thêm những trường hợp business-specific như duplicate params, nhiều values cho một scalar parameter, Unicode whitespace, số quá lớn ngoài miền `Integer`, email sai định dạng, nested forms và group-specific validation nếu ứng dụng yêu cầu.

## 10. Vì sao Integer phù hợp hơn int khi cần phát hiện thiếu?

Dùng `int` cho một trường bắt buộc rất dễ lẫn giữa “không có input” và “có giá trị 0”. Một primitive của Java không thể chứa null; tùy đường binding, conversion và constructor invocation, giá trị mặc định hoặc lỗi chuyển kiểu có thể xuất hiện. Đừng dựa vào một hành vi ngầm của binder khi thực sự muốn biểu diễn **missing**.

Nên dùng:

```java
public record QuantityForm(
        @NotNull @Min(1) Integer quantity
) {}
```

thay vì dựa vào:

```java
public record QuantityForm(
        @Min(1) int quantity
) {}
```

Với `Integer`, nếu tham số vắng mặt dẫn tới null, `@NotNull` phát hiện yêu cầu bắt buộc. Với `int`, số 0 có thể trộn lẫn “client gửi 0” và “không có input”; nếu cần phân biệt hai trạng thái này, đừng dùng primitive làm input DTO thành phần đó.

**Không phải lúc nào cũng nên dùng Integer:** nếu domain cho phép mặc định 0 và việc vắng mặt có nghĩa rõ ràng tương tự 0, primitive có thể phù hợp. Hãy quyết định theo API contract, không theo tiện lợi của syntax.

## 11. Record compact constructor: validation trước hay sau?

Java cho phép compact constructor:

```java
public record StrictForm(String displayName, Integer age) {
    public StrictForm {
        if (displayName == null) {
            throw new IllegalArgumentException("Missing displayName");
        }
    }
}
```

Với constructor này, nếu `displayName` thiếu và Spring/Jackson truyền null, constructor có thể ném exception **ngay trong quá trình tạo object**. Khi object không được tạo, không thể mặc định mong `@Valid` trên object sẽ sinh `FieldError NotBlank`.

Đây là sự khác biệt lớn trong kiểm thử:

- **Bean Validation trên record components:** phù hợp khi muốn gom nhiều field errors vào một `BindingResult`.
- **Constructor guard clauses:** phù hợp cho bất biến không bao giờ được phép tạo object trong domain, nhưng phải có chiến lược mapping exception rõ. Không tự nhận mọi `IllegalArgumentException` từ constructor là lỗi input HTTP 400.
- **Controller DTO vs domain record:** có thể dùng một input record cho phép trạng thái tạm thời không hợp lệ (để thu thập errors), sau khi validate thì chuyển nó thành một domain type có invariant mạnh.

Ví dụ pipeline:

```text
HTTP -> FormSignup DTO (có thể chứa null)
     -> @Valid / BindingResult
     -> nếu hợp lệ: mapping + domain constructor
     -> service / persistence
```

Không dùng domain constructor throw để thay thế toàn bộ input error collection nếu UI cần trả nhiều lỗi một lần.

## 12. Nested records và thiếu dữ liệu con

Constructor binding có thể dựng đối tượng lồng nhau thông qua nested paths. Ví dụ **snippet minh họa**:

```java
public record Address(
        @NotBlank String city,
        String postalCode
) {}

public record CheckoutForm(
        @Valid @NotNull Address address,
        @NotNull Integer quantity
) {}
```

Client form có thể gửi:

```text
address.city=Hanoi&address.postalCode=100000&quantity=2
```

Spring constructor binding hỗ trợ nested objects và collection parameters, nhưng khi **toàn bộ nested object bị thiếu**, hành vi tạo instance/null và errors có thể phụ thuộc kiểu, resolver và cấu hình. Vì vậy cần kiểm thử:

1. Không có `address` hoặc `address.*`.
2. Có `address.city` nhưng thiếu `address.postalCode`.
3. `address.city=`.
4. `address` có nhiều level.
5. Có collection keys `items[0].sku`, `items[1].sku`.
6. Một indexed field chứa giá trị không chuyển kiểu được.

Nếu `address` thực sự là bắt buộc, `@NotNull` ở parent cần có, `@Valid` giúp cascade tới constraints bên trong khi nested object tồn tại. `@Valid` không tự thay thế `@NotNull` cho reference null.

`DataBinder#setAutoGrowNestedPaths` là option cho bean property binding và **không nên dùng như lời giải thích mặc định cho constructor binding**. Với Spring Framework 6.1, Javadoc phân biệt auto-grow setter/field paths với recursive constructor binding. Hai kỹ thuật có cơ chế khác.

## 13. Đổi tên tham số, formatter và lỗi chuyển kiểu

### 13.1. @BindParam không đổi property Java

Trong form demo:

```java
@BindParam("display-name") String displayName
```

Spring tra request parameter `display-name` cho constructor component `displayName`. `FieldError#getField()` thường tham chiếu Java property `displayName`. Đừng cho frontend so sánh error field với tên input HTML mà không có mapping khi dùng alias.

### 13.2. ConversionService chịu trách nhiệm kiểu dữ liệu form

Form data đều là text; Spring MVC dùng conversion service và formatters để chuyển:

- `"22"` → `Integer 22`.
- `"2026-11-06"` → `LocalDate` khi format rules phù hợp.
- `"ACTIVE"` → enum khi converter/formatter hỗ trợ.
- `"true"` → Boolean khi representation được chấp nhận.
- List/map keys qua indexed paths, với giới hạn về size/complexity.

Với ngày tháng, ví dụ:

```java
public record AppointmentForm(
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate visitDate
) {}
```

đây là **snippet minh họa** cần imports `java.time.LocalDate` và `org.springframework.format.annotation.DateTimeFormat`. Kiểm thử ngày hợp lệ, thiếu ngày, ngày sai format và invalid calendar date. Không coi format error là `@NotNull` violation.

### 13.3. Đừng đoán mọi sai kiểu đều thành cùng một exception

Một conversion failure có thể được ghi trong `BindingResult` với `typeMismatch`, hoặc dẫn tới exception sớm hơn nếu object construction fails. Đường `@ModelAttribute` có khác biệt với Jackson `@RequestBody`. Khi xây handler production:

- Dùng `BindingResult` nếu muốn trả nhiều field errors.
- Dùng advice cho `MethodArgumentNotValidException` khi không có `BindingResult`.
- Xử lý malformed JSON qua `HttpMessageNotReadableException`.
- Xác minh các constructor exceptions đặc biệt trên framework version thực tế.
- Không catch mọi `RuntimeException` rồi trả cùng lỗi 400.
- Không phản chiếu raw exception message/rejected values ra client.

## 14. Những khác biệt khi chạy validation groups và method validation

`@Valid` kích hoạt nhóm mặc định `Default` của Bean Validation. Nếu ứng dụng có Create/Update groups:

```java
public interface OnCreate {}
public interface OnUpdate {}

public record EditForm(
        @NotBlank(groups = OnCreate.class) String name,
        @NotNull(groups = OnUpdate.class) Long id
) {}
```

thì cần `@Validated(OnCreate.class)` hoặc `@Validated(OnUpdate.class)` tại boundary thích hợp để chọn nhóm. Đây là snippet minh họa, không thuộc runnable demo.

Một record thiếu `id` có thể hợp lệ ở Create nhưng không hợp lệ ở Update theo thiết kế, **không phải vì constructor binding biết phân biệt hai nghiệp vụ**. Hãy test đúng nhóm cho từng endpoint.

Từ Spring MVC 6.1, các direct constraints trên method parameters hoặc return values có thể kích hoạt **method validation** và `HandlerMethodValidationException` thay vì `MethodArgumentNotValidException`. Nếu muốn test `@ModelAttribute` route đúng như bài demo, đừng vô tình thêm `@Min` trực tiếp vào một parameter khác trên handler rồi giả định exception types không đổi.

### 14.1. BindingResult luôn đứng sát argument

Đúng:

```java
void submit(
        @Valid @ModelAttribute SignupForm form,
        BindingResult result) {
}
```

Sai:

```java
void submit(
        @Valid @ModelAttribute SignupForm form,
        @RequestParam String source,
        BindingResult result) {
}
```

Hai đoạn trên là chữ ký method **minh họa**, không phải source file để biên dịch độc lập. `BindingResult` phải đứng **ngay sau** đối tượng mà nó mô tả. Vị trí sai có thể gây lỗi resolve arguments thay vì đưa errors vào controller.

## 15. Kiểm thử lỗi không chỉ dựa vào HTTP status

Một test chỉ viết:

```java
.andExpect(status().isBadRequest())
```

chưa đủ để chứng minh constructor binding đúng. HTTP 400 có thể đến từ:

- `@NotNull` vì missing field.
- `@NotBlank` vì null/blank.
- `typeMismatch` khi string không chuyển được sang số.
- JSON parser không đọc được request.
- Unsupported content-type hoặc missing parameter khác.
- Exception tùy chỉnh từ constructor.

Vì vậy với mỗi tình huống, test nên assert:

- `code` cấp response như `VALIDATION_ERROR` / `INVALID_JSON`.
- `field` được chỉ ra đúng, nhất là với `@BindParam`.
- `FieldError#getCode()` hoặc một business error code ổn định.
- Số lượng lỗi khi có nhiều required fields.
- Kết quả thành công khi dữ liệu đầy đủ.
- Dữ liệu optional không khiến request bị từ chối.
- Input thừa không được gán vào trường privileged.

### 15.1. Tránh dependency vào thứ tự provider

`BindingResult#getFieldErrors()` không nên được diễn giải là “lỗi đầu tiên theo thứ tự khai báo record”. Nếu HTTP contract cần thứ tự, sort trong adapter. Trong demo, `ErrorMapper` sort theo `field` rồi `code` và tests mới dùng `errors[0]`/`errors[1]`.

### 15.2. Một field có nhiều constraints

Nếu khai báo:

```java
@NotBlank
@Size(min = 3, max = 30)
String displayName
```

và client gửi `" "`, có thể sinh cả `NotBlank` và `Size`. Không dùng `Map<String,String>` ghi đè mọi lỗi trên cùng field nếu cần hiển thị đầy đủ. Hãy trả `List<FieldIssue>` hoặc định nghĩa rule priority rõ ràng (ví dụ required trước length).

### 15.3. Test theo trạng thái “missing” thay vì luôn dựa vào message

Với `@NotNull`/`@NotBlank`, default message có thể được nội suy theo locale/provider. Nên assert stable code và field; kiểm thử i18n message là một bộ test riêng khi product có translation contract. Không hardcode chuỗi tiếng Anh “must not be blank” trong mọi test constructor binding.

## 16. Lỗi phổ biến trong dự án Spring thực tế

**1. Nghĩ record tự yêu cầu mọi field.** Record không có setter nhưng canonical constructor vẫn có thể nhận null reference components.

**2. Thiếu @NotNull cho kiểu Integer.** `@Min`/`@Max` không tự cấm null; đối tượng thiếu tuổi có thể không bị từ chối.

**3. Dùng int khi phải phân biệt “không gửi” với “gửi 0”.** Primitive không có null, tạo semantics khó kiểm chứng.

**4. Chỉ test full form.** Không phát hiện vấn đề missing field, blank field hoặc type conversion.

**5. Nghĩ @RequestParam(required=true) tự áp vào record components.** `@ModelAttribute` là cơ chế binding khác.

**6. Dựa vào DataBinder#setRequiredFields cho constructor binding.** Javadoc 6.1 giới hạn option này cho `bind(PropertyValues)`, không phải `construct(...)`.

**7. Dùng Bean Validation để bắt JSON sai cú pháp.** Nếu deserialization thất bại thì chưa có object để validate.

**8. Nhầm @BindParam với Jackson @JsonProperty.** Một annotation tùy biến tên request parameter cho Spring constructor binder không quyết định JSON property names.

**9. Đặt BindingResult sai vị trí.** Phải liền kề `@ModelAttribute` argument.

**10. Nghĩ lỗi sai kiểu luôn là @NotNull.** Conversion failure có cơ chế riêng, có thể là `typeMismatch` hoặc exception giai đoạn tạo object.

**11. Dùng compact constructor ném IllegalArgumentException rồi mong @Valid trả đầy đủ errors.** Constructor có thể chặn việc tạo object trước validation.

**12. Bind thẳng vào JPA entity.** Có nguy cơ mass assignment; dùng dedicated input DTO record/allowlist và authorization.

**13. Cho record chứa field privileged.** Immutable không ngăn client cung cấp role/ownerId nếu đã đưa chúng vào constructor parameters.

**14. Dùng @Email và nghĩ email bắt buộc.** `@Email` cho phép null; nếu bắt buộc, thêm `@NotBlank`.

**15. Quên @Valid trên handler.** Constraint annotations trên DTO không tự chạy trong mọi tình huống.

**16. Dùng javax.validation với Spring Boot 3.** Boot 3 dùng Jakarta namespace.

**17. Test mỗi HTTP 400.** Không biết do Bean Validation, conversion hay parser.

**18. Hardcode messages tiếng Anh từ provider.** Default messages khác theo locale/version; assert field/code.

**19. Coi nested @Valid cũng là @NotNull.** `@Valid` cascade khi object có mặt; null phải bị chặn riêng nếu bắt buộc.

**20. Dùng @ModelAttribute ngầm trong native image.** Nên khai báo tường minh để hỗ trợ AOT reflection hints tốt hơn.

**21. Quên flag -parameters khi có constructor-bound Java classes thông thường.** Spring 6.1 không còn đọc local variable table để suy ra tên tham số theo cách cũ.

**22. Gắn các method constraints trực tiếp rồi coi exception type giữ nguyên.** Spring MVC 6.1 có method validation riêng.

**23. Trả FieldError#getRejectedValue() trong API JSON.** Có thể lộ dữ liệu nhạy cảm.

**24. Dùng setAllowedFields rồi nghĩ đã chặn constructor argument không mong muốn.** Allowed fields chủ yếu giới hạn property binding; constructor input shape phải được thiết kế đúng.

**25. Đánh đồng HTTP form params với JSON.** Jackson và WebDataBinder có conversion, alias và failure modes khác nhau.

## 17. Checklist code review cho constructor binding test

1. DTO là record riêng cho input, chỉ chứa trường client được phép cấp?
2. `@ModelAttribute` được khai báo tường minh cho form/query?
3. Record có canonical constructor đơn giản, không ném exception khi cần thu thập nhiều lỗi input?
4. Các reference components bắt buộc có `@NotNull`/`@NotBlank` thích hợp?
5. Có phân biệt `@Min` không cấm null và `@Email` không cấm null?
6. Có test missing key khác với key rỗng, whitespace và sai kiểu?
7. Có test optional components bị thiếu vẫn hợp lệ?
8. Có test alias `@BindParam` bằng tên input thực tế?
9. Có test gửi sai alias và input thừa?
10. `BindingResult` có đứng sát argument được kiểm tra?
11. Endpoint không có `BindingResult` có handler `MethodArgumentNotValidException` đúng?
12. JSON endpoints có test incomplete/null/malformed riêng?
13. Có tránh đánh đồng `DataBinder#setRequiredFields` với constructor requirements?
14. Nếu dùng `declarativeBinding`, có hiểu nó không thay đổi constructor parameter allowlist?
15. Có khai báo `-parameters` và test Spring Framework version thực tế?
16. Có lọc dữ liệu nhạy cảm khi xây error response?
17. Có test order ổn định của errors nếu JSON array thứ tự là contract?
18. Nếu record nested có `@Valid` và `@NotNull` đúng cấp?
19. Nếu có validation groups, có test Create/Update độc lập?
20. Nếu có method validation, có phân loại `HandlerMethodValidationException`?
21. Không dùng JPA entity làm request DTO chỉ để tiện mapping?
22. Khi nâng Boot/Jackson, có chạy regression test cho missing creator properties?

**Kết luận:** Kiểm thử constructor binding với record phải chứng minh cả **khả năng tạo object từ input hợp lệ** và **hành vi đúng với dữ liệu thiếu hoặc sai**. Immutable record không tự làm mọi trường thành bắt buộc; `@NotBlank`/`@NotNull` mới biểu diễn hợp đồng required khi sử dụng Bean Validation. `@ModelAttribute` và `@RequestBody` có cơ chế tạo object khác nhau. Hãy test hai đường riêng biệt, assert loại lỗi và field, giữ `BindingResult` đúng vị trí, bảo vệ khỏi input thừa và không dựa vào các default ngầm khó kiểm chứng.

## 18. Tài liệu tham khảo

- [Spring Framework — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): primary constructor binding, `@BindParam`, `BindingResult` và validation.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html): `DataBinder.construct`, nested constructor binding, conversion errors.
- [Spring Framework — MVC Data Binding and Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html): immutable DTO và constructor binding vì an toàn dữ liệu.
- [Spring Framework — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html): `declarativeBinding` và allowed fields.
- [Spring Framework 6.1 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html): `construct` và giới hạn `setRequiredFields`.
- [Spring Framework 6.1 — BindParam Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/bind/annotation/BindParam.html): tên input của constructor parameter.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `MethodArgumentNotValidException` và `HandlerMethodValidationException`.
- [Spring Framework 6.1 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes): constructor binding và `-parameters`.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): `@NotNull`, `@NotBlank`, `@Valid` và validation groups.

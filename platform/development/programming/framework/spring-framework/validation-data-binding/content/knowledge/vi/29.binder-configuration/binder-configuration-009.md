# Thay thế hoặc bổ sung validator mà không vô tình mất bộ mặc định trong Spring MVC

## 1. Bài toán: thêm một quy tắc nhỏ nhưng làm mất `@NotBlank`

Bạn đang có một form đăng ký được Spring MVC kiểm tra bằng Jakarta Validation:

```java
public class SignupForm {
    @NotBlank
    private String username;

    @Email
    private String email;

    // getters/setters...
}
```

Bây giờ nghiệp vụ yêu cầu cấm các tên `admin` và `root`. Bạn viết một Spring `Validator`:

```java
public final class ReservedUsernameValidator implements Validator {
    @Override
    public boolean supports(Class<?> clazz) {
        return SignupForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        if ("admin".equalsIgnoreCase(form.getUsername())
                || "root".equalsIgnoreCase(form.getUsername())) {
            errors.rejectValue(
                    "username", "username.reserved", "Tên đã dành riêng");
        }
    }
}
```

Đây là đoạn minh họa, cần import `org.springframework.validation.Validator`, `Errors` và có lớp `SignupForm` hoàn chỉnh. Nếu đăng ký trong controller bằng:

```java
@InitBinder("signupForm")
void initBinder(WebDataBinder binder) {
    binder.setValidator(new ReservedUsernameValidator());
}
```

bạn có thể vô tình **thay thế** validator Bean Validation toàn cục đã được framework gắn vào binder. Lúc đó custom rule vẫn chạy, nhưng `@NotBlank`, `@Email` và các constraint khác không còn được chính binder ấy đánh giá nữa.

Trong ứng dụng Spring MVC thông thường, khi muốn **bổ sung** một Spring Validator cục bộ bên cạnh bộ mặc định, hãy dùng:

```java
@InitBinder("signupForm")
void initBinder(WebDataBinder binder) {
    binder.addValidators(new ReservedUsernameValidator());
}
```

**Nguyên tắc cốt lõi:** `addValidators(...)` là hành động **bổ sung**; `setValidator(...)` và `replaceValidators(...)` là hành động **thiết lập lại danh sách**. Muốn thay thế thực sự phải chủ động, hiểu hậu quả và kiểm thử tất cả ràng buộc còn cần giữ.

Bài học hướng đến Spring Framework 6.2.x / Spring Boot 3.5.x, Java 17+, **Spring MVC Servlet stack**. Khái niệm `DataBinder` cũng có ở nơi khác, nhưng luồng áp dụng `@InitBinder`, argument resolver và exception trên WebFlux có khác biệt. Không đánh đồng với AOP method validation.

## 2. Ba tầng nên phân biệt ngay từ đầu

Một request form đến controller thường đi qua các bước:

```text
HTTP form/query parameters
           |
           v
Spring MVC argument resolver
           |
           v
WebDataBinder tạo cho model attribute
           |
           +-- global Validator (nếu MVC đã cấu hình)
           |
           +-- @InitBinder trong ControllerAdvice
           |
           +-- @InitBinder trong Controller
           |
           v
bind / convert request fields thành DTO
           |
           v
@Valid / @Validated yêu cầu kiểm tra
           |
           +-- gọi các validators đang được áp dụng
           |
           v
BindingResult (FieldError/ObjectError)
           |
           +-- có BindingResult ngay sau DTO -> handler xử lý
           |
           +-- không có -> MVC có thể ném
               MethodArgumentNotValidException
```

Sơ đồ là mô hình khái niệm, không khẳng định mọi argument resolver luôn tạo binder với cùng một đối tượng đích. Cần nhận diện ba khái niệm:

1. **Jakarta Bean Validation provider:** đọc các annotation `jakarta.validation.constraints.*` như `@NotBlank`, `@Email`, `@Min`, `@Valid`, groups.
2. **Spring `org.springframework.validation.Validator`:** hợp đồng gồm `supports(Class<?>)` và `validate(Object, Errors)`, thích hợp cho quy tắc riêng và báo lỗi vào `BindingResult`.
3. **Spring `DataBinder` / `WebDataBinder`:** giữ danh sách những validator sẽ được áp dụng khi có một lệnh validation thích hợp; danh sách có thể được cấu hình toàn cục và bổ sung cục bộ.

Một `LocalValidatorFactoryBean` của Spring là **cầu nối** quan trọng: nó triển khai cả `jakarta.validation.Validator` lẫn `org.springframework.validation.Validator` (và hỗ trợ validation hints), giúp chuyển `ConstraintViolation` của Jakarta sang `FieldError`/`ObjectError` của Spring.

Vì vậy “bộ validator mặc định” trong bối cảnh **MVC request binding** thường là Bean Validation adapter `LocalValidatorFactoryBean`, chứ không phải một thuật toán hard-code riêng trong controller.

## 3. Khi nào Spring có validator mặc định?

Spring MVC, khi Bean Validation provider có mặt và được tích hợp vào cấu hình MVC, mặc định có thể đăng ký `LocalValidatorFactoryBean` làm global Validator cho `@Valid`/`@Validated` trên controller arguments.

Với Spring Boot 3.x, cấu hình phụ thuộc thông thường:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

- `spring-boot-starter-web` cung cấp Spring MVC Servlet.
- `spring-boot-starter-validation` cung cấp Jakarta Validation provider, thường là Hibernate Validator và integration liên quan.
- Spring Boot có thể auto-configure một `LocalValidatorFactoryBean` nếu điều kiện phù hợp; một dự án tự cấu hình validator có thể thay đổi hành vi.
- Nếu không có provider phù hợp trên classpath, **không nên suy luận** rằng chỉ đặt `@NotBlank` vào DTO thì mọi request tự được kiểm tra.

**Không nhầm:** Spring Boot có bean global trong application context không chứng minh rằng mọi binder đang dùng chính bean đó. Controller `@InitBinder`, `WebMvcConfigurer#getValidator()`, `@ControllerAdvice` hoặc cấu hình XML có thể ảnh hưởng danh sách được gắn vào một binder cụ thể.

Khi thay cấu hình, luôn xác minh **hành vi thực tế** bằng test: thử dữ liệu sai cho cả constraint annotation và custom rule. Đừng chỉ kiểm tra application context có khởi động thành công.

## 4. Các API cấu hình validator trên `DataBinder`

Spring `DataBinder` cung cấp những method quan trọng sau:

| API | Tác động trên danh sách | Dùng khi nào |
| --- | --- | --- |
| `setValidator(Validator validator)` | **Xóa các validator hiện có**, rồi đặt validator được truyền vào (nếu khác null) | Cố ý muốn danh sách chỉ còn một validator |
| `addValidators(Validator... validators)` | **Thêm** các validator vào danh sách đang có | Bổ sung rule cục bộ, giữ mặc định |
| `replaceValidators(Validator... validators)` | **Xóa danh sách hiện có** rồi thay bằng chính danh sách được truyền vào | Chủ động kiểm soát toàn bộ tập validators |
| `getValidator()` | Trả validator **đầu tiên** trong danh sách, hoặc null | Xem primary validator, không đại diện đầy đủ cho tất cả |
| `getValidators()` | Trả danh sách các validator đã cấu hình | Kiểm tra thành phần và thứ tự |
| `setExcludedValidators(Predicate<Validator>)` | Thiết lập predicate lọc validator bị loại khỏi tập **được áp dụng** | Trường hợp đặc biệt cần tạm tránh validator nào đó; có từ Spring 6.1 |
| `getValidatorsToApply()` | Trả danh sách sau khi áp điều kiện exclude | Debug chính xác những validator được chạy; có từ Spring 6.1 |
| `validate()` / `validate(hints...)` | **Thực thi** validator(s) được áp dụng, ghi lỗi vào `BindingResult` | Programmatic validation hoặc MVC thực thi khi có trigger |

### 4.1. Bảng trạng thái dễ nhớ

Giả sử một binder ban đầu có danh sách:

```text
[BeanValidationAdapter]
```

Và có thêm `LocalBusinessValidator`:

| Lệnh gọi | Danh sách kết quả |
| --- | --- |
| `binder.addValidators(local)` | `[BeanValidationAdapter, LocalBusinessValidator]` |
| `binder.setValidator(local)` | `[LocalBusinessValidator]` |
| `binder.replaceValidators(local)` | `[LocalBusinessValidator]` |
| `binder.replaceValidators(defaultValidator, local)` | `[BeanValidationAdapter, LocalBusinessValidator]` |
| `binder.setValidator(null)` | `[]` |

Đây là minh họa khi binder ban đầu thật sự có `BeanValidationAdapter` và không có những validator khác. Không giả định Spring tự thêm adapter vào mọi `new DataBinder(target)` do bạn tạo bằng tay: với binder programmatic, bạn thường phải cấu hình nó trực tiếp.

### 4.2. Cẩn thận với `getValidator()`

`binder.getValidator()` chỉ trả **validator đầu tiên**, không phải “danh sách kết hợp” và cũng không phải bảo đảm nó luôn là Bean Validation adapter:

```java
Validator primary = binder.getValidator();
List<Validator> configured = binder.getValidators();
```

Đoạn minh họa dùng import `org.springframework.validation.Validator` và `java.util.List`. Với nhiều validators, xem `getValidators()` để biết toàn bộ; ở Spring 6.1+ có thể đối chiếu thêm `getValidatorsToApply()` để thấy tác động của excluded predicate.

Không sửa trực tiếp danh sách trả về bởi `getValidators()`; Spring trả danh sách chỉ đọc. Sử dụng đúng API `addValidators`/`replaceValidators`.

## 5. Cách an toàn mặc định: `binder.addValidators(...)`

Giả sử `SignupForm` có ràng buộc Jakarta và `ReservedUsernameValidator` là custom Spring Validator.

```java
@RestController
@RequestMapping("/signups")
public class SignupController {

    private final ReservedUsernameValidator usernameValidator;

    public SignupController(ReservedUsernameValidator usernameValidator) {
        this.usernameValidator = usernameValidator;
    }

    @InitBinder("signupForm")
    void initSignupBinder(WebDataBinder binder) {
        binder.addValidators(usernameValidator);
    }

    @PostMapping("/form")
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult errors) {
        // ...
    }
}
```

Đây là mẫu minh họa; project biên dịch đầy đủ ở phần 10.

Ý nghĩa:
- `@InitBinder("signupForm")` chỉ chọn các binders có object name `signupForm`.
- `binder.addValidators(usernameValidator)` **không xóa** các validators đã được global MVC config đưa vào binder.
- `@Valid` ở `@ModelAttribute` kích hoạt bước Bean Validation/Spring validators trong phạm vi argument validation thông thường.
- `BindingResult` đứng **ngay sau** DTO và chứa lỗi do cả hai nguồn tạo ra.
- Nếu bỏ `@Valid`/`@Validated` khỏi argument mà không gọi `binder.validate()` cách khác, đừng mặc định custom validator tự được kích hoạt chỉ vì nó đã được đăng ký.

Đây cũng là mẫu Spring Framework khuyến nghị khi muốn thêm custom validator tại controller mà vẫn giữ Bean Validation adapter global.

### 5.1. Vì sao cần giới hạn `@InitBinder` theo tên?

Với:

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.addValidators(usernameValidator);
}
```

một controller có nhiều DTO có thể tạo binder cho loại khác `SignupForm`. Custom validator `supports()` chỉ hỗ trợ `SignupForm` nên có thể không tương thích với target khác. `DataBinder` kiểm tra khả năng hỗ trợ target khi đăng ký; trong những tình huống mismatch nó có thể ném `IllegalStateException` thay vì âm thầm bỏ qua rule.

Giải pháp:
- Giới hạn `@InitBinder("signupForm")` khi chỉ muốn áp cho một model attribute.
- Hoặc kiểm tra target/targetType trước khi thêm nếu có lý do cấu hình chung.
- Để validator cục bộ hỗ trợ **đúng type**, không trả `true` cho mọi class chỉ để né lỗi.

Đừng thay một validator “không hỗ trợ target” bằng cách gọi `setValidator(null)` để né exception: như vậy có thể xóa cả bộ mặc định cần giữ.

## 6. Vì sao `setValidator(...)` nguy hiểm trong `@InitBinder`?

`setValidator` không có nghĩa “đặt validator phụ trợ” hay “bật validation”. Nó **thay toàn bộ danh sách hiện có** bằng validator được truyền.

Sai lầm:

```java
@InitBinder("signupForm")
void initBinder(WebDataBinder binder) {
    binder.setValidator(usernameValidator);
}
```

Giả sử global `LocalValidatorFactoryBean` ban đầu biết kiểm tra `@NotBlank`, `@Email`, `@Min`. Sau lệnh trên, validator đó bị gỡ khỏi danh sách của binder này. Chỉ còn custom rule. Khi người dùng gửi `email="bad"` nhưng username không thuộc danh sách cấm, request có thể **được chấp nhận** dù `@Email` thất bại trong một validator Bean Validation thực sự.

Cách sửa:

```java
@InitBinder("signupForm")
void initBinder(WebDataBinder binder) {
    binder.addValidators(usernameValidator);
}
```

Chỉ sử dụng `setValidator(...)` khi bạn **chủ động muốn thay thế hoàn toàn**. Ví dụ một object đặc biệt cần validator độc quyền, và bạn đã xác nhận không còn phụ thuộc vào annotation constraints ở đường binding đó.

### 6.1. Cạm bẫy `setValidator(null)`

```java
binder.setValidator(null);
```

Lệnh này có thể làm **trống danh sách validator** trên binder, không chỉ “reset custom validator của chúng ta”. Nếu mục đích là tắt một rule cục bộ, hãy cân nhắc cấu trúc lại phạm vi đăng ký, chia controller/DTO, hoặc chính sách exclusion có kiểm soát. Không dùng lệnh này như một thủ thuật xử lý ngoại lệ khi test không hiểu nguyên nhân.

### 6.2. Cạm bẫy ở `@ControllerAdvice`

Nếu một `@ControllerAdvice` dùng:

```java
@ControllerAdvice
public class GlobalBinderAdvice {

    @InitBinder
    void init(WebDataBinder binder) {
        binder.setValidator(someCustomValidator);
    }
}
```

mọi binder chịu ảnh hưởng của advice có nguy cơ bị thay global validator bằng custom rule. Sau đó một controller dùng `binder.addValidators(...)` chỉ bổ sung trên danh sách **đã bị sửa**; không thể hồi phục default bị mất bằng cách “add thêm lần nữa” trừ khi nó có đúng reference tới default validator.

Do đó, các chính sách toàn cục cần được thiết kế và kiểm thử cẩn thận hơn chính sách cục bộ. Nếu chỉ có một form đặc thù, ưu tiên `@InitBinder("formName")` ở controller hoặc advice với phạm vi hẹp.

## 7. `replaceValidators(...)`: chỉ dùng khi đã xác định tập đầy đủ

`replaceValidators(Validator... validators)` hữu ích khi muốn **chọn đúng những validator** phải áp cho một binder.

Ví dụ chủ động giữ cả mặc định và custom:

```java
Validator defaultValidator = /* reference đã được xác minh */;
Validator localValidator = new ReservedUsernameValidator();

binder.replaceValidators(defaultValidator, localValidator);
```

Đây là fragment minh họa, không tự tạo được `defaultValidator` bằng comment. Đừng giả định `binder.getValidator()` luôn là default adapter nếu một `@ControllerAdvice` hoặc một bước cấu hình trước đó đã thay danh sách.

Với binder đã có đúng danh sách mong muốn, **`addValidators` đơn giản và ít rủi ro hơn**. Còn khi cần `replaceValidators`, hãy:
1. Xác định chính xác những validators đang cần giữ.
2. Lấy references từ nguồn cấu hình tin cậy.
3. Đảm bảo tất cả đều hỗ trợ target.
4. Kiểm tra thứ tự và có hay không các validators trùng.
5. Test vi phạm từ **từng** rule phải tồn tại sau replacement.

### 7.1. Không dùng danh sách cũ mà chưa hiểu nguồn

```java
List<Validator> before = binder.getValidators();
binder.replaceValidators(localValidator);
```

Bạn đã lưu danh sách để xem log nhưng không đưa chúng vào danh sách mới: validators cũ đã mất. Nếu thực sự muốn giữ tất cả, `addValidators(localValidator)` là lời gọi diễn đạt đúng ý định.

Nếu muốn thay một validator cụ thể, hãy tạo danh sách mới từ các thành phần đã được xác minh và dùng `replaceValidators(...)`, đồng thời tính đến thứ tự, duplicates và chính sách exclusion. Không nên viết code phức tạp chỉ để làm việc `addValidators` vốn đã hỗ trợ.

### 7.2. `setExcludedValidators` và danh sách được áp dụng

Từ Spring Framework 6.1, có:

```java
binder.setExcludedValidators(
        validator -> validator instanceof LegacyValidator);
```

`LegacyValidator` ở đây là kiểu minh họa, không phải class mặc định của Spring. Predicate làm cho các validator phù hợp bị loại khỏi **tập validator thực sự được chạy**; nó không có nghĩa người dùng xóa object khỏi `getValidators()`. Dùng `getValidatorsToApply()` nếu cần debug danh sách hiệu lực.

**Rủi ro:** Một predicate quá rộng có thể vô tình exclude chính `LocalValidatorFactoryBean`, khiến Bean Validation constraints bị bỏ qua dù `getValidators()` vẫn cho thấy nó đang được cấu hình.

Nếu không có yêu cầu cụ thể, không cần `setExcludedValidators`. API này phù hợp hơn cho các trường hợp tích hợp/loại trừ đã được kiểm thử rõ ràng.

## 8. Spring `Validator` khác Jakarta `Validator` thế nào?

Trong một dự án Spring Boot 3+, tên `Validator` xuất hiện ở **hai package khác nhau**:

```java
org.springframework.validation.Validator
jakarta.validation.Validator
```

Chúng không có cùng chữ ký.

### 8.1. Spring Validator

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

- Kiểm tra một object và ghi lỗi vào `org.springframework.validation.Errors`.
- Thường dùng `errors.reject(...)` hoặc `errors.rejectValue("field", "code")`.
- Có thể đăng ký qua `WebDataBinder#addValidators`.
- Dễ tùy biến theo một controller hoặc form cụ thể.

### 8.2. Jakarta Validator

```java
jakarta.validation.Validator validator = ...;

Set<ConstraintViolation<SignupForm>> violations =
        validator.validate(form);
```

- Đọc annotation constraints, có groups và cascade `@Valid`.
- Trả `Set<ConstraintViolation<T>>`, không trực tiếp ghi `BindingResult`.
- Không dùng trực tiếp `jakarta.validation.Validator` làm argument cho `binder.addValidators(...)`; method đó nhận Spring `Validator`.

### 8.3. Cầu nối `LocalValidatorFactoryBean`

`org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` triển khai **cả hai** API. Khi được dùng như Spring Validator, nó thực hiện Jakarta Bean Validation và chuyển violations thành Spring errors tương ứng.

Lược đồ:

```text
@Valid @ModelAttribute SignupForm
             |
             v
Spring WebDataBinder.validate()
             |
             +--> LocalValidatorFactoryBean
             |       |
             |       +--> Jakarta provider: @NotBlank, @Email, @Min
             |       |
             |       +--> Spring FieldError / ObjectError
             |
             +--> ReservedUsernameValidator
                     |
                     +--> errors.rejectValue(...)
             |
             v
       BindingResult gộp lỗi
```

**Không nên tạo mới `LocalValidatorFactoryBean` cho từng request**: việc bootstrap provider tốn tài nguyên và có vòng đời riêng. Dùng bean do Spring quản lý, hoặc để Spring MVC global configuration tự cung cấp khi đủ điều kiện.

## 9. `SmartValidator`, validation hints và groups

Spring `SmartValidator` mở rộng Spring `Validator`:

```java
public interface SmartValidator extends Validator {
    void validate(Object target, Errors errors, Object... validationHints);
}
```

`LocalValidatorFactoryBean` triển khai `SmartValidator` để hỗ trợ các hints như validation groups. Khi handler dùng `@Validated(Publish.class)`, thông tin group có thể được truyền cho validator hỗ trợ hints.

Ví dụ:

```java
public interface Publish {}

public class SignupForm {

    @NotBlank
    private String username;

    @NotBlank(groups = Publish.class)
    private String approvalCode;
}
```

Đây là **fragment minh họa**, khác DTO trong project ở phần 10. Nếu handler dùng:

```java
public ResponseEntity<?> publish(
        @Validated(Publish.class)
        @ModelAttribute("signupForm") SignupForm form,
        BindingResult errors) {
    // ...
}
```

thì chỉ các constraint thuộc `Publish` được yêu cầu theo quy tắc Jakarta Validation (không tự gộp `Default`). Nếu muốn cả hai, có thể dùng `@Validated({Default.class, Publish.class})` với import `jakarta.validation.groups.Default`.

**Sắc thái quan trọng:** Một custom Spring `Validator` chỉ triển khai `validate(Object, Errors)` vẫn có thể được gọi khi có validation hints; nó **không tự hiểu groups**. Nếu business rule phải phụ thuộc vào group, hãy triển khai `SmartValidator` và xử lý hints có chủ đích, hoặc viết custom Jakarta `@Constraint` có `groups`.

Đừng hiểu `addValidators` là Spring tự “chuyển đổi” mọi custom rule thành một Jakarta constraint có groups.

## 10. Project hoàn chỉnh: Java 17 + Spring Boot 3.5.6

Ta xây một API form đăng ký với:
- `@NotBlank` cho `username` và `email`.
- `@Email` cho đúng định dạng email.
- `@NotNull` + `@Min(18)` cho độ tuổi.
- Custom rule cấm username `admin`/`root`.
- `@InitBinder("signupForm")` gọi **`addValidators`**, không thay global validator.
- `BindingResult` trả danh sách field + mã lỗi ổn định.
- MockMvc tests đảm bảo cả Jakarta và custom rule còn chạy.
- Unit/integration tests riêng cho `DataBinder` chứng minh sự khác nhau giữa `addValidators`, `setValidator`, `replaceValidators`.

Chúng ta dùng Java 17, Spring MVC Servlet, Spring Boot **3.5.6** làm một bản phát hành minh họa cố định, không ngụ ý đây là bản Boot mới nhất. Mỗi file dưới đây là mã hoàn chỉnh trong cấu trúc đã nêu, không cần chép các fragments khác vào project.

### 10.1. Cấu trúc

```text
binder-validators-demo/
├── pom.xml
├── src/main/java/demo/validation/
│   ├── BinderValidationApplication.java
│   ├── SignupForm.java
│   ├── OtherForm.java
│   ├── ReservedUsernameValidator.java
│   └── SignupController.java
└── src/test/java/demo/validation/
    ├── SignupControllerTest.java
    └── BinderCompositionTest.java
```

### 10.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>binder-validators-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
```

Không tự thêm một Bean Validation provider thứ hai vào `pom.xml` nếu starter đã quản lý nó. Việc giữ một provider tương thích giúp tránh xung đột cấu hình giữa `javax.validation` và `jakarta.validation`.

### 10.3. `BinderValidationApplication.java`

```java
package demo.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BinderValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(BinderValidationApplication.class, args);
    }
}
```

### 10.4. `SignupForm.java`

```java
package demo.validation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank(message = "username.required")
    private String username;

    @NotBlank(message = "email.required")
    @Email(message = "email.invalid")
    private String email;

    @NotNull(message = "age.required")
    @Min(value = 18, message = "age.min")
    private Integer age;

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
```

Sử dụng `Integer` + `@NotNull` để phân biệt tuổi bị thiếu (null) với tuổi bằng 0. `@Min` tự nó thường coi null là hợp lệ; `@NotNull` đảm bảo dữ liệu bắt buộc.

### 10.5. `OtherForm.java`

```java
package demo.validation;

public class OtherForm {

    private String username;

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }
}
```

Đây chỉ là form **đối chứng** để cho thấy phạm vi `@InitBinder("signupForm")`. Việc `OtherForm` không dùng cùng rule trong demo không ngụ ý mọi API ngoài đời được phép chấp nhận username đặc biệt.

### 10.6. `ReservedUsernameValidator.java`

```java
package demo.validation;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class ReservedUsernameValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return SignupForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        String username = form.getUsername();

        if (username != null
                && ("admin".equalsIgnoreCase(username)
                    || "root".equalsIgnoreCase(username))) {

            errors.rejectValue(
                    "username",
                    "username.reserved",
                    "This username is reserved");
        }
    }
}
```

- `supports()` giới hạn validator cho `SignupForm` và subclasses, nếu có.
- `validate()` chỉ kiểm tra danh sách tên riêng, không tự tái triển khai `@NotBlank`/`@Email`/`@Min`.
- `errors.rejectValue(...)` thêm `FieldError` vào cùng `BindingResult` mà MVC đang xử lý.
- Validator không thực hiện I/O, không thay đổi target, không giữ state request.

Chính sự **tách trách nhiệm** này làm lỗi mất Bean Validation dễ quan sát: khi chỉ còn custom validator, input email sai sẽ không bị custom rule chặn.

### 10.7. `SignupController.java`

```java
package demo.validation;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/signups")
public class SignupController {

    private final ReservedUsernameValidator reserved;

    public SignupController(ReservedUsernameValidator reserved) {
        this.reserved = reserved;
    }

    @InitBinder("signupForm")
    void configure(WebDataBinder binder) {
        // THÊM, KHÔNG THAY: giữ Bean Validation đã có.
        binder.addValidators(reserved);
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> form(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            var entries = errors.getFieldErrors().stream()
                    .map(error -> {
                        String[] codes = error.getCodes();
                        // Chọn mã chung cuối cùng thay vì prefix theo object.
                        String code = codes != null && codes.length > 0
                                ? codes[codes.length - 1]
                                : "unknown";
                        return error.getField() + ":" + code;
                    })
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "status", "invalid",
                    "errors", entries));
        }

        return ResponseEntity.ok(Map.of(
                "status", "created",
                "username", form.getUsername()));
    }

    @PostMapping(path = "/other",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, String> other(
            @ModelAttribute("otherForm") OtherForm form) {

        return Map.of("username", form.getUsername());
    }
}
```

**Vì sao dùng mã cuối của `FieldError.getCodes()`?** `DefaultMessageCodesResolver` tạo các mã lỗi theo thứ tự từ cụ thể đến tổng quát, ví dụ `NotBlank.signupForm.username`, `NotBlank.username`, `NotBlank.java.lang.String`, `NotBlank`. Lấy phần tử cuối giúp demo trả `username:NotBlank` không phụ thuộc object name. Đây là lựa chọn format response đơn giản cho bài học; production có thể có bảng mapping error codes riêng và localization.

**Lưu ý khi dùng `Map.of`:** Endpoint thành công chỉ sử dụng `username` đã được `@NotBlank` kiểm tra nên không null trong đường chạy hợp lệ. `OtherForm` endpoint được dùng trong test với username có giá trị; nếu để null và gọi `Map.of` sẽ gây lỗi. Một API production nên xử lý null rõ ràng hoặc dùng response DTO.

### 10.8. `SignupControllerTest.java` — test đi qua Spring MVC

```java
package demo.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    @Autowired
    MockMvc mvc;

    private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder
            signup(String username, String email, String age) {

        return post("/signups/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", username)
                .param("email", email)
                .param("age", age);
    }

    @Test
    void validFormIsAccepted() throws Exception {
        mvc.perform(signup("Lan", "lan@example.com", "20"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("created"))
                .andExpect(jsonPath("$.username").value("Lan"));
    }

    @Test
    void jakartaNotBlankIsStillActive() throws Exception {
        mvc.perform(signup("", "lan@example.com", "20"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("username:NotBlank")));
    }

    @Test
    void jakartaEmailIsStillActive() throws Exception {
        mvc.perform(signup("Lan", "bad-email", "20"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("email:Email")));
    }

    @Test
    void jakartaMinIsStillActive() throws Exception {
        mvc.perform(signup("Lan", "lan@example.com", "16"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("age:Min")));
    }

    @Test
    void jakartaNotNullIsStillActive() throws Exception {
        mvc.perform(post("/signups/form")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("username", "Lan")
                        .param("email", "lan@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("age:NotNull")));
    }

    @Test
    void localReservedRuleIsActive() throws Exception {
        mvc.perform(signup("admin", "lan@example.com", "20"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("username:username.reserved")));
    }

    @Test
    void jakartaAndLocalErrorsAppearTogether() throws Exception {
        mvc.perform(signup("root", "wrong", "16"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("username:username.reserved")))
                .andExpect(jsonPath("$.errors", hasItem("email:Email")))
                .andExpect(jsonPath("$.errors", hasItem("age:Min")));
    }

    @Test
    void conversionErrorIsNotBeanValidation() throws Exception {
        mvc.perform(signup("Lan", "lan@example.com", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors",
                        hasItem("age:typeMismatch")));
    }

    @Test
    void binderScopeDoesNotAffectOtherForm() throws Exception {
        mvc.perform(post("/signups/other")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("username", "root"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("root"));
    }
}
```

Có **9 test** MVC:
- Test positive có đủ dữ liệu hợp lệ.
- Bốn test xác minh những constraint Jakarta riêng biệt vẫn chạy (`@NotBlank`, `@Email`, `@Min`, `@NotNull`).
- Test reserved username chứng minh rule custom được bổ sung.
- Test kết hợp chứng minh **cả hai bộ** cùng ghi errors.
- Test type mismatch phân biệt binding với validation.
- Test form khác kiểm tra phạm vi `@InitBinder("signupForm")`.

Nếu một ai đó đổi `binder.addValidators(reserved)` thành `binder.setValidator(reserved)` trong controller, các test `jakartaNotBlankIsStillActive`, `jakartaEmailIsStillActive`, `jakartaMinIsStillActive` và `jakartaNotNullIsStillActive` dự kiến sẽ phát hiện regression. Đó là lý do suite này có giá trị hơn một test chỉ kiểm tra username `admin`.

### 10.9. `BinderCompositionTest.java` — test đặc biệt cho `DataBinder`

Test này minh họa rõ sự khác nhau **mà không cần gửi HTTP request**. Ta chủ động tạo `DataBinder` trong test và cung cấp default adapter, vì `new DataBinder(...)` thuần **không tự lấy MVC global validator**.

```java
package demo.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.validation.DataBinder;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class BinderCompositionTest {

    @Autowired
    LocalValidatorFactoryBean beanValidationAdapter;

    @Autowired
    ReservedUsernameValidator localValidator;

    private SignupForm invalidInput() {
        SignupForm form = new SignupForm();
        form.setUsername("admin");
        form.setEmail("bad-email");
        form.setAge(16);
        return form;
    }

    private DataBinder newBinder() {
        return new DataBinder(invalidInput(), "signupForm");
    }

    @Test
    void addValidatorsPreservesDefaultAndCustom() {
        DataBinder binder = newBinder();
        binder.setValidator(beanValidationAdapter);
        binder.addValidators(localValidator);
        binder.validate();

        var errors = binder.getBindingResult();
        assertTrue(errors.hasFieldErrors("username"));
        assertTrue(errors.hasFieldErrors("email"));
        assertTrue(errors.hasFieldErrors("age"));
        assertEquals(2, binder.getValidators().size());
    }

    @Test
    void setValidatorReplacesThePreviouslyConfiguredOne() {
        DataBinder binder = newBinder();
        binder.setValidator(beanValidationAdapter);

        // Cố tình làm SAI trong test đối chứng.
        binder.setValidator(localValidator);
        binder.validate();

        var errors = binder.getBindingResult();
        assertTrue(errors.hasFieldErrors("username"));
        assertFalse(errors.hasFieldErrors("email"));
        assertFalse(errors.hasFieldErrors("age"));
        assertEquals(1, binder.getValidators().size());
    }

    @Test
    void replaceValidatorsCanExplicitlyPreserveBoth() {
        DataBinder binder = newBinder();
        binder.setValidator(beanValidationAdapter);

        // Khi thật sự cần replace, kê khai đủ cả hai.
        binder.replaceValidators(beanValidationAdapter, localValidator);
        binder.validate();

        var errors = binder.getBindingResult();
        assertTrue(errors.hasFieldErrors("username"));
        assertTrue(errors.hasFieldErrors("email"));
        assertTrue(errors.hasFieldErrors("age"));
        assertEquals(2, binder.getValidators().size());
    }
}
```

**Không hiểu nhầm test đối chứng:** `setValidatorReplacesThePreviouslyConfiguredOne()` **pass** khi xác nhận Bean Validation bị mất, vì mục tiêu của test là chứng minh hành vi destructive của `setValidator`. Production code vẫn phải dùng `addValidators` hoặc một replacement giữ đủ danh sách cần thiết.

Test inject `LocalValidatorFactoryBean` do Spring Boot Validation auto-configuration cung cấp trong cấu hình minh họa. Ở một project tùy biến đã có nhiều validator beans hoặc không có default adapter, injection cần `@Qualifier`/`@Primary` phù hợp và test phải xác nhận mình đang dùng đúng Bean Validation adapter của ứng dụng.

### 10.10. Chạy kiểm thử

Trong thư mục `binder-validators-demo` với JDK 17+ và Maven có thể tải dependencies:

```bash
mvn test
```

Dự kiến tổng cộng **12 tests**: 9 MockMvc + 3 DataBinder. Code không có stdout nghiệp vụ cố định; Maven/Surefire sẽ thông báo số test theo môi trường. Các test dùng assertions cho status, field codes, số lượng validators và việc mất/bảo toàn constraint.

Để chạy ứng dụng:

```bash
mvn spring-boot:run
```

Trong ví dụ này không cần tạo một `MethodValidationPostProcessor` thủ công; chủ đề là **MVC binder validation**, không phải AOP method validation.

## 11. Thử bằng curl: thấy hai bộ rules cùng chạy

### 11.1. Form hợp lệ

```bash
curl -i -X POST 'http://localhost:8080/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=Lan' \
  --data-urlencode 'email=lan@example.com' \
  --data-urlencode 'age=20'
```

Kỳ vọng HTTP **200** và JSON tương đương:

```json
{"status":"created","username":"Lan"}
```

### 11.2. Sai rule Jakarta

```bash
curl -i -X POST 'http://localhost:8080/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=Lan' \
  --data-urlencode 'email=bad-email' \
  --data-urlencode 'age=20'
```

Kỳ vọng HTTP **400**, body có error code `email:Email`. Nếu bạn sửa `addValidators` thành `setValidator` và chỉ còn custom validator, cùng request có thể bị chấp nhận sai.

### 11.3. Sai rule cục bộ

```bash
curl -i -X POST 'http://localhost:8080/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin' \
  --data-urlencode 'email=lan@example.com' \
  --data-urlencode 'age=20'
```

Kỳ vọng HTTP **400**, body có `username:username.reserved`. Nếu bạn vô tình bỏ `addValidators` nhưng vẫn giữ provider mặc định, request này có thể không bị chặn.

### 11.4. Hai nguồn lỗi cùng lúc

```bash
curl -i -X POST 'http://localhost:8080/signups/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=root' \
  --data-urlencode 'email=wrong' \
  --data-urlencode 'age=16'
```

Kỳ vọng HTTP **400**; danh sách `errors` chứa các mã:

```json
{
  "status": "invalid",
  "errors": [
    "age:Min",
    "email:Email",
    "username:username.reserved"
  ]
}
```

Đây là danh sách đã `sorted()` trong controller, nên thứ tự ví dụ rõ ràng. Thứ tự thực thi validator hoặc thứ tự duyệt `ConstraintViolation` **không** được dựa vào để sắp xếp business priorities.

## 12. Kiểm chứng cấu hình validator thực tế

### 12.1. Đừng chỉ nhìn `getValidator()`

Trong `@InitBinder`, để debug khi cần:

```java
@InitBinder("signupForm")
void inspect(WebDataBinder binder) {
    var before = binder.getValidators();
    binder.addValidators(reserved);
    var after = binder.getValidators();

    // Dùng before/after để debug kiểm soát trong môi trường test.
}
```

Đây là fragment minh họa **thay thế** `configure(...)` trong project, không phải một method cần đăng ký thêm cạnh method cũ. Mục đích là quan sát danh sách thành phần. `getValidator()` chỉ trả primary entry, còn `getValidators()` trả danh sách cấu hình.

Không log toàn bộ target object/raw request vì có thể chứa mật khẩu và dữ liệu cá nhân. Nếu cần instrumentation, log class names và số lượng validators, hoặc assert trực tiếp trong integration test.

### 12.2. Điều gì xảy ra với excluded validators?

Một cấu hình có thể có:

```java
binder.setExcludedValidators(
        v -> v.getClass().getSimpleName().contains("Legacy"));
```

Đây là ví dụ biểu diễn API, **không phải cách lọc đáng tin cậy cho production** vì dựa vào tên class. Predicate tạo khác biệt giữa `getValidators()` và `getValidatorsToApply()`. Nếu exclusion tình cờ khớp Bean Validation adapter, Jakarta constraints bị bỏ khỏi nhánh binder validation dù danh sách cấu hình trông vẫn đầy đủ.

Khi debug “validator có trong list nhưng không chạy”, hãy xem **danh sách được áp dụng** và điều kiện exclude, không chỉ danh sách được khai báo.

### 12.3. `supports(Class<?>)` không phải tùy chọn

`DataBinder` có logic kiểm tra validator có hỗ trợ kiểu target hay không trong lúc thêm/đặt validator. Một `ReservedUsernameValidator` chỉ dành cho `SignupForm` không nên cài vào binder dành cho `PaymentForm`, `AddressForm` hoặc cả application context không phân biệt.

Nếu muốn áp logic chung cho nhiều lớp, có thể:
- Định nghĩa một interface chung được hỗ trợ, ví dụ `HasUsername`, và validator hỗ trợ các implementation thực sự.
- Dùng Jakarta custom constraint trên field cần kiểm tra, cho phép reuse giữa DTOs.
- Chọn đúng object name/target type khi đăng ký validator.

Không sửa `supports` thành `return true` nếu validator vẫn ép kiểu `(SignupForm) target`: khi target khác kiểu, sẽ nhận `ClassCastException` trong runtime.

## 13. Phối hợp `@ControllerAdvice` và validator cục bộ

Spring MVC cho phép đặt `@InitBinder` ở `@ControllerAdvice`. Ví dụ:

```java
@ControllerAdvice(assignableTypes = SignupController.class)
public class SignupAdvice {

    private final CommonSignupValidator common;

    public SignupAdvice(CommonSignupValidator common) {
        this.common = common;
    }

    @InitBinder("signupForm")
    void configure(WebDataBinder binder) {
        binder.addValidators(common);
    }
}
```

Đây là đoạn minh họa, cần định nghĩa `CommonSignupValidator` và imports Spring; **không nằm trong project chạy** ở phần 10.

Nếu controller còn có `@InitBinder` riêng, cả advice và controller có thể tác động tới cùng binder. Nếu một nơi dùng `setValidator(...)` sau khi nơi khác đã `addValidators(...)`, danh sách cuối có thể khác ý định. **Thứ tự áp dụng cấu hình quan trọng**, nhưng trong code nghiệp vụ hãy ưu tiên API additive thay vì phụ thuộc vào một thứ tự mỏng manh.

Một nguyên tắc tổ chức tốt:
- Global Bean Validation được cấu hình tại MVC infrastructure.
- Common validators có phạm vi rõ ở advice.
- Form-specific validators được add tại controller.
- Tránh gọi `setValidator`/`replaceValidators` khi không có chủ đích thay tập validators.
- Test điểm hội tụ ở handler thực, thay vì chỉ unit test riêng từng validator.

## 14. Tùy chỉnh validator toàn cục không giống bổ sung validator cục bộ

Khi cần thay validator của **toàn bộ Spring MVC**, có thể cấu hình `WebMvcConfigurer#getValidator()`:

```java
@Configuration
public class MvcValidationConfig implements WebMvcConfigurer {

    @Override
    public Validator getValidator() {
        return customGlobalValidator;
    }
}
```

Đây là **đoạn kiến trúc minh họa**, cần định nghĩa biến `customGlobalValidator` và các imports. Nó không nằm trong project chạy ở phần 10.

Lệnh trên nói với MVC **dùng validator được cung cấp làm validator toàn cục**, không đơn thuần bổ sung một rule. Nếu trả về một Spring Validator chỉ kiểm tra username và không thực hiện Bean Validation, bạn có thể thay thế tích hợp mặc định của toàn bộ MVC. Đó là một quyết định có phạm vi rộng hơn rất nhiều so với `@InitBinder("signupForm")`.

Nếu mục tiêu chỉ là:
- Cấm một username trong một form → `@InitBinder` + `addValidators`.
- Tạo một quy tắc dùng chung trên nhiều DTO → custom Jakarta `@Constraint` hoặc Spring Validator phù hợp.
- Đổi thông điệp/constraint factory/interpolator của Bean Validation toàn cục → tùy chỉnh `LocalValidatorFactoryBean`/Boot validation configuration, giữ vai trò Jakarta provider.
- Chọn một Validator toàn cục hoàn toàn khác → chỉ làm khi bạn chủ động thay kiến trúc validation và có regression test.

Không “cài tạm” một global `getValidator()` chỉ để một endpoint hết lỗi validation.

## 15. Nếu thật sự phải thay: hai chiến lược an toàn

### 15.1. Thay bằng adapter biết gọi cả Jakarta lẫn custom

Có thể tạo một **composite Spring Validator** thực thi hai nguồn rule. Nhưng khi làm vậy, cần:
- Tự quản lý thứ tự và duplicate.
- Giữ validation groups/hints nếu cần; tùy trường hợp phải triển khai `SmartValidator`.
- Chuyển lỗi của Jakarta provider sang Spring `Errors` thông qua adapter.
- Đảm bảo xử lý target types và exception nhất quán.

Chỉ nên viết composite khi kiến trúc cần rõ ràng một abstraction chung; trường hợp thông thường `binder.addValidators(...)` đã cung cấp composition sẵn.

### 15.2. Dùng `replaceValidators` với danh sách đầy đủ

Đoạn minh họa programmatic:

```java
DataBinder binder = new DataBinder(form, "signupForm");

binder.replaceValidators(beanValidationAdapter, customValidator);
binder.validate();

BindingResult result = binder.getBindingResult();
```

Ở đây giả sử `form`, `beanValidationAdapter`, `customValidator` đều đã được tạo và hỗ trợ target. Khác với `new DataBinder(...); replaceValidators(customValidator)`, phương án này **cố ý giữ** Jakarta adapter.

Không nên dùng `replaceValidators` để “tự động chữa” một binder bị cấu hình sai mà không biết trạng thái ban đầu. Mọi replacement trên đường HTTP production cần có integration tests cho các constraint cơ bản và business rules.

## 16. Trường hợp `@RequestBody`, `@ModelAttribute` và method validation

### 16.1. Form/`@ModelAttribute` là ví dụ rõ nhất

```java
@PostMapping("/form")
public ResponseEntity<?> register(
        @Valid @ModelAttribute("signupForm") SignupForm form,
        BindingResult errors) {
    // ...
}
```

Trong ngữ cảnh này, `WebDataBinder` tham gia binding và validation. `@InitBinder("signupForm")` giúp thêm Spring Validator cục bộ. Đây là ngữ cảnh chính của project chạy ở phần 10.

### 16.2. JSON/`@RequestBody` cũng có validation nhưng kênh binding khác

```java
@PostMapping("/json")
public ResponseEntity<?> register(
        @Valid @RequestBody SignupForm form) {
    // ...
}
```

Đối tượng JSON thường được `HttpMessageConverter`/Jackson deserialize. Spring MVC vẫn có thể tạo binder cho bước validation sau conversion, và `@InitBinder` có thể ảnh hưởng tới danh sách validators tùy object name/hạ tầng. Tuy nhiên, **các quy tắc property binding** như `setAllowedFields(...)` không thể dùng để chặn Jackson gán field khi decode JSON.

Đừng khẳng định `@InitBinder` “không bao giờ chạy” với JSON; cũng đừng dựa vào whitelist setter binding để bảo vệ deserialization. Nếu cần cấm một property JSON, dùng input DTO riêng và thực thi authorization ở service.

### 16.3. Direct method constraints có nhánh riêng

Từ Spring Framework 6.1, khi một controller handler có `@Min`, `@NotBlank`... **trực tiếp** trên method parameters hoặc trên method return, MVC có built-in method validation. Nó có thể thay thế argument validation riêng và báo `HandlerMethodValidationException` thay vì `MethodArgumentNotValidException`.

Ví dụ:

```java
@PostMapping("/mixed")
public String mixed(
        @RequestParam("n") @Min(1) int n,
        @Valid @ModelAttribute("signupForm") SignupForm form) {
    // ...
}
```

Đây là fragment minh họa, không có trong project chạy ở phần 10. **Phạm vi validators của MVC argument binder và method validation** không phải lúc nào cũng giống nhau; nếu handler chuyển sang method validation do direct constraints, cần test lại việc custom Spring Validator được gọi ở điểm nào. Đặc biệt, custom `org.springframework.validation.Validator` cục bộ không tự trở thành Jakarta `ConstraintValidator` của executable validation.

Vì bài tập tập trung vào tránh làm mất default binder validator, ví dụ chạy chính **không đặt direct method constraint** trên handler. Điều này giúp các test xác định đúng nhánh binder/`BindingResult`.

### 16.4. Service `@Validated` qua AOP cũng khác

`@Service @Validated` cộng `MethodValidationPostProcessor` kiểm tra method parameters/return khi invocation đi qua Spring proxy. Nó không nhận danh sách validators của một `WebDataBinder` cụ thể đã dùng trong request khác. Đừng mong một rule được `@InitBinder` add ở controller tự động bảo vệ mọi service call.

Nếu cần cùng một rule ở HTTP form và service, cân nhắc triển khai constraint/domain validation dùng chung tại tầng phù hợp.

## 17. Validation và conversion/binding errors là hai nguồn độc lập

Một form nhập `age=abc` khi property `age` là `Integer` có thể thất bại **trước** bước Bean Validation. Spring ghi lỗi `typeMismatch` trong `BindingResult`, ngay cả khi bean validator vẫn tồn tại.

Ngược lại:
- `age=16` chuyển được sang integer nhưng vi phạm `@Min(18)`.
- `age` hoàn toàn vắng mặt dẫn đến `null` và vi phạm `@NotNull`.
- `username=admin` hợp lệ về kiểu và có ký tự, nhưng vi phạm custom rule.
- `email=bad-email` bind được thành String nhưng vi phạm `@Email`.
- `username=""` vi phạm `@NotBlank`, không nhất thiết được custom reserved rule phát hiện.

Nếu chỉ thấy handler trả 400, không thể kết luận có đủ validators hay không. Hãy kiểm tra **mã lỗi** hoặc nguồn tạo `FieldError` để biết nhánh nào đã chạy.

Không dùng một broad exception handler trả 400 cho mọi `ValidationException`: có những lỗi provider/configuration là lỗi lập trình phía server, không phải sai request.

## 18. Checklist kiểm tra trước khi merge thay đổi binder

1. **Xác định ý định:** muốn **bổ sung** hay **thay thế** một Validator?
2. Nếu bổ sung, dùng **`addValidators`**, không dùng `setValidator` chỉ vì nhìn tên quen.
3. Kiểm tra Spring Boot đã có `spring-boot-starter-validation` và global Jakarta adapter chưa.
4. Đọc đúng package `org.springframework.validation.Validator` so với `jakarta.validation.Validator`.
5. Với custom Spring Validator, `supports(Class<?>)` phải khớp DTO.
6. Giới hạn `@InitBinder("objectName")` cho form cần rule; đừng làm ảnh hưởng DTO khác.
7. Nếu dùng `@ControllerAdvice`, xem các binder callbacks có thể chồng lên nhau.
8. Tránh `WebMvcConfigurer#getValidator()` tùy tiện vì đó là thay cấu hình toàn cục.
9. Nếu dùng `replaceValidators`, truyền **đủ** validators cần giữ, không chỉ cái vừa viết.
10. Kiểm tra `getValidators()` và `getValidatorsToApply()` (Spring 6.1+) khi có chính sách exclusion.
11. Thử một input sai đối với **mỗi rule Jakarta** quan trọng: `@NotBlank`, `@Email`, `@NotNull`, `@Min`...
12. Thử một input sai với **custom rule**; không chỉ kiểm tra rule mặc định.
13. Thử **cùng lúc** hai lỗi, đối chiếu đều xuất hiện trong `BindingResult`.
14. Test cả input thiếu, rỗng, null, sai kiểu và đúng kiểu nhưng ngoài miền giá trị.
15. Xem `@Valid`/`@Validated` có ở argument tương ứng không; đăng ký validator không tự kích hoạt validate.
16. Nếu dùng groups, phân biệt Spring `SmartValidator` với plain `Validator` và kiểm tra hint handling.
17. Nếu controller chuyển sang MVC built-in method validation do direct constraints, test lại cơ chế chạy custom rule.
18. Test qua `MockMvc` thay vì chỉ gọi thẳng controller Java, vì cần chứng minh MVC binder factory đã chạy.
19. Không để property admin/role/security-sensitive được bind tùy tiện; validation không thay authorization.
20. Cân nhắc log chỉ metadata lỗi, không ghi raw giá trị nhạy cảm.

## 19. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `binder.setValidator(local)` để “thêm” custom rule | Mất validators đang có | `binder.addValidators(local)` |
| `binder.replaceValidators(local)` không truyền default | Mất Jakarta Bean Validation adapter | Chỉ replace khi có đủ danh sách cần giữ |
| `binder.setValidator(null)` để “reset rule” | Xóa hết validators của binder | Thiết kế lại phạm vi hoặc dùng cấu hình exclusion có kiểm soát |
| Dùng `getValidator()` để khẳng định chỉ có một validator | Bỏ sót các validators khác | Kiểm tra `getValidators()` |
| Không xét `setExcludedValidators` | Validator có trong list nhưng không được áp dụng | Kiểm tra `getValidatorsToApply()` |
| Thêm một validator chỉ supports `SignupForm` vào mọi binder | Có thể ném `IllegalStateException` hoặc gây lỗi cast | Dùng `@InitBinder("signupForm")`/kiểm tra type |
| Tạo bean `jakarta.validation.Validator` rồi đưa thẳng vào `addValidators` | Sai interface Spring API | Dùng Spring `Validator` hoặc `LocalValidatorFactoryBean` adapter |
| Chỉ có `@Valid` nhưng không có provider | Constraints có thể không chạy như kỳ vọng | Cấu hình starter/provider và test invalid input |
| Quên `@Valid` trên request argument | Validators đã đăng ký nhưng chưa được kích hoạt | Bổ sung annotation/trigger đúng |
| Chỉ test input `username=admin` | Custom rule chạy nhưng mất `@Email` vẫn không phát hiện | Test cả default và custom |
| Dùng `@Validated(Publish.class)` tưởng `Default` luôn chạy | Có thể bỏ qua group Default | Chọn groups chính xác |
| Spring custom `Validator` không xét hints nhưng mong tự đổi theo groups | Chạy rule ngoài ý định | Dùng `SmartValidator` hoặc Jakarta constraint có groups |
| Nhầm lỗi `typeMismatch` với `@Min` | Bắt sai nguồn lỗi | Phân biệt binding và validation errors |
| Gắn rules vào `@ControllerAdvice` toàn cục không xét target | Ảnh hưởng form khác | Thu hẹp advice hoặc dùng object name |
| Đặt class-level `@Validated` cho controller chỉ để dùng validator | Có thể đổi sang AOP validation | Dùng `@Valid` hoặc parameter-level groups và MVC built-in |
| Coi Bean Validation là authorization | Request vẫn có thể sửa quyền khi DTO thiết kế sai | DTO riêng + service/security policy |

## 20. Bài tập thực hành

1. Đổi `binder.addValidators(reserved)` thành `binder.setValidator(reserved)` trong project. Chạy test và chỉ rõ những test Jakarta nào mất bảo vệ.
2. Dùng `binder.replaceValidators(defaultValidator, reserved)` trong test programmatic; phân biệt kết quả với `replaceValidators(reserved)`.
3. Gửi cùng lúc `username=root`, `email=wrong`, `age=16`. Vì sao có thể nhận đủ ba mã lỗi?
4. Bỏ `@Valid` khỏi `@ModelAttribute SignupForm`, giữ nguyên `@InitBinder`. Dự đoán những test invalid nào có thể thay đổi kết quả.
5. Thêm `@Size(min=4)` trên username, viết test giúp chứng minh thêm constraint Jakarta vẫn hoạt động sau khi add custom rule.
6. Thêm validator thứ hai kiểm tra domain email nội bộ. Dùng `addValidators` và test cả hai custom rules cùng tồn tại với Jakarta adapter.
7. Đặt `@InitBinder` không có `"signupForm"` và kiểm thử endpoint `/signups/other`. Giải thích vai trò `supports()` và object name.
8. Tạo nhóm `Publish` và `@Validated({Default.class, Publish.class})` trên argument, kiểm tra custom Spring Validator có chạy và có xét hint không.
9. Thử `setExcludedValidators(...)` với predicate loại một validator riêng và so sánh `getValidators()` với `getValidatorsToApply()`.
10. Tạo một DTO record và dùng constructor binding; so sánh validation với mutable form và setter binding, chú ý không nhầm binding policy với validator list.
11. Thay cách báo lỗi trong `SignupController` bằng một error DTO có `field`, `code`, `message`, không trả rejected raw values.
12. Mở rộng test để đảm bảo một thay đổi ở `@ControllerAdvice` không xóa validator mặc định của controller khác.

**Tóm tắt:** Khi cấu hình binder trong Spring MVC, hãy phân biệt **add** (bổ sung rule), **set/replace** (thay toàn bộ danh sách) và **exclude** (lọc lúc áp dụng). Để bổ sung custom validator mà không mất Jakarta Bean Validation mặc định, thông thường dùng `@InitBinder("formName")` + `binder.addValidators(custom)`, giữ `@Valid`/`@Validated` đúng chỗ, và viết regression tests cho cả hai nguồn lỗi.

## 21. Tài liệu chính thức

- [Spring Framework 6.2 — Spring MVC Validator configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — `@InitBinder`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — `DataBinder` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — Java Bean Validation và `LocalValidatorFactoryBean`](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — MVC argument/method validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — `BindingResult` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Boot 3.5 — MockMvc testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
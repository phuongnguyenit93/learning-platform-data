# Phân biệt `jakarta.validation.Validator` và Spring `Validator`

## 1. Vì sao cùng một ứng dụng có hai `Validator`?

Spring Framework hỗ trợ cả **Jakarta Bean Validation** (chuẩn Jakarta) và **Spring Validation** (API riêng của Spring). Hai interface đều tên `Validator`, nhưng không có cùng kiểu trả về, cách viết quy tắc hay kiểu dữ liệu lỗi:

- `jakarta.validation.Validator`: đánh giá các **constraint** như `@NotBlank`, `@Min`, `@Size` trên object và **trả về `Set<ConstraintViolation<T>>`**.
- `org.springframework.validation.Validator`: kiểm tra object theo logic Java trong lớp triển khai và **ghi lỗi vào `Errors`/`BindingResult`** do caller cung cấp.

Ví dụ yêu cầu đăng ký có tên không được để trống và tuổi từ 18: Jakarta có thể dùng annotation `@NotBlank`, `@Min`; Spring Validator có thể kiểm tra trong `validate(...)` và gọi `errors.rejectValue(...)`.

Điểm đặc biệt của Spring là **`LocalValidatorFactoryBean` kết nối hai API**: nó tạo và quản lý Jakarta provider, đồng thời cho phép kết quả Jakarta xuất hiện dưới dạng lỗi Spring phục vụ binding/form. Bài học này làm rõ trách nhiệm của mỗi interface và cách sử dụng đúng trong Spring MVC.

## 2. So sánh API qua bảng

| Nội dung | `jakarta.validation.Validator` | `org.springframework.validation.Validator` |
| --- | --- | --- |
| Hệ sinh thái | Jakarta Validation, không phụ thuộc Spring | Spring Framework |
| Định nghĩa ràng buộc | Thường dùng annotation và `ConstraintValidator` | Thường viết Java trực tiếp |
| Hàm chính | `validate(T object, Class<?>... groups)` | `supports(Class<?>)`, `validate(Object, Errors)` |
| Kiểu trả về khi kiểm tra | `Set<ConstraintViolation<T>>` | `void`; lỗi được thêm vào `Errors` |
| Chi tiết lỗi | Constraint, property path, message, invalid value | `FieldError`, `ObjectError`, code, message arguments |
| Nhóm validation | Có `groups`/`Default` và group sequence | Interface cơ bản không nhận groups; `SmartValidator` nhận hints |
| Validation theo property | `validateProperty`, `validateValue` | Chủ động kiểm tra/ghi lỗi field |
| Tích hợp Spring MVC | Qua provider và Spring adapter | Qua `DataBinder`/`WebDataBinder`/`BindingResult` |
| Cần thư viện chạy? | Cần provider thực thi, ví dụ Hibernate Validator | Custom validator chỉ cần Spring Validation |

**Lưu ý:** dữ liệu vi phạm constraint **không khiến** Jakarta `validate(...)` tự ném exception theo mặc định; nó trả tập lỗi. Spring `validate(Object, Errors)` cũng không tự ném exception vì object không hợp lệ; việc xử lý HTTP 400 hoặc exception phụ thuộc tầng gọi và cấu hình.

### Đừng import nhầm hai interface

```java
// Hai package khác nhau, cùng tên ngắn Validator:
jakarta.validation.Validator beanValidator;
org.springframework.validation.Validator springValidator;
```

Đây là khai báo biến để so sánh kiểu. Trong tệp cần dùng cả hai, hãy viết tên đầy đủ như trên, hoặc chỉ import một kiểu. Việc `import jakarta.validation.Validator` rồi gọi `supports(...)` sẽ không biên dịch vì Jakarta interface không định nghĩa phương thức ấy.

## 3. Jakarta Bean Validation: constraint, violation, groups

### 3.1. Tạo quy tắc khai báo

Một form/DTO thường đặt annotation lên thuộc tính:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class SignupForm {

    @NotBlank(message = "name.required")
    private String name;

    @Min(value = 18, message = "age.tooYoung")
    private int age;

    // Constructor, getter/setter theo cách binding của ứng dụng
}
```

Đây là **đoạn minh họa khai báo**, chưa phải file Java tự chạy. `@NotBlank` không chấp nhận `null`, chuỗi rỗng hoặc toàn khoảng trắng. `@Min(18)` kiểm tra số ít nhất là 18. Một constraint được thực hiện bởi provider (ví dụ Hibernate Validator), không phải chỉ bởi `jakarta.validation-api`.

Gọi Jakarta interface:

```java
Set<ConstraintViolation<SignupForm>> violations =
        jakartaValidator.validate(form);
```

Mỗi `ConstraintViolation<T>` có thể cho biết:

- `getPropertyPath()`: field/path, như `name` hoặc `address.city`.
- `getMessage()`: thông điệp đã được nội suy.
- `getMessageTemplate()`: mẫu thông điệp ban đầu.
- `getInvalidValue()`: giá trị bị từ chối, cần tránh log hoặc trả về khi chứa dữ liệu nhạy cảm.
- `getConstraintDescriptor()`: metadata constraint (annotation, attributes, groups...).
- `getRootBean()`: object gốc, khi có.

**`Set` không cam kết thứ tự.** Không mặc định dùng “phần tử đầu tiên” làm lỗi ưu tiên trong API. Nếu cần kết quả deterministic, hãy sắp xếp theo field/code.

Jakarta còn có:

```java
jakartaValidator.validateProperty(form, "name");
jakartaValidator.validateValue(SignupForm.class, "name", "");
jakartaValidator.getConstraintsForClass(SignupForm.class);
```

`validateProperty` kiểm tra ràng buộc của một property trên object đang có; `validateValue` kiểm tra giá trị giả định mà chưa cần object; `getConstraintsForClass` tra metadata. Hai phương thức kiểm tra property/value không tương đương validate toàn bộ đồ thị object/cascade.

### 3.2. Validation groups

Mặc định, `jakartaValidator.validate(form)` chạy constraints thuộc nhóm `jakarta.validation.groups.Default`. Với nhóm riêng:

```java
interface PublishChecks {}

Set<ConstraintViolation<SignupForm>> violations =
        jakartaValidator.validate(form, PublishChecks.class);
```

Đoạn này giả định có constraint gắn `groups = PublishChecks.class`; nếu tất cả constraint chỉ thuộc `Default`, gọi nhóm riêng không có nghĩa chúng vẫn được chạy. Group sequence và kế thừa nhóm là các cơ chế nâng cao cần cân nhắc riêng.

Khi model có object lồng nhau, muốn cascade xuống object con, đánh dấu quan hệ bằng `@jakarta.validation.Valid`:

```java
@jakarta.validation.Valid
private Address address;
```

Chỉ đặt `@NotNull` ở property `address` không tự đánh giá các annotation bên trong `Address`. Jakarta Bean Validation cũng có executable validation cho method parameter và return value qua `forExecutables()`.

## 4. Spring Validator: `supports`, `validate`, `Errors`

Interface Spring định nghĩa hai phương thức cốt lõi:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, org.springframework.validation.Errors errors);
}
```

Đây là chữ ký rút gọn để học; khi viết code hãy implement `org.springframework.validation.Validator` thực tế.

`supports(Class<?>)` thông báo loại object mà validator hiểu được. `validate(Object, Errors)` thực hiện logic kiểm tra và ghi lỗi:

- `errors.rejectValue("name", "name.required")`: lỗi gắn với field cụ thể.
- `errors.reject("date.range.invalid")`: lỗi cấp object.
- `errors.hasErrors()`, `errors.getFieldErrors()`, `errors.getGlobalErrors()`: truy xuất lỗi đã ghi.

`Errors` thường được dùng thông qua `BindingResult`, vốn hỗ trợ thêm thông tin về data binding, lỗi chuyển kiểu và giá trị field bị từ chối. `FieldError` có **error code**, field và default message; code có thể được giải quyết bằng Spring `MessageSource`. `ConstraintViolation.getMessage()` của Jakarta là thông điệp đã được nội suy ở Jakarta provider. Không nên xem hai giá trị đó là cùng một loại dữ liệu.

Ví dụ custom Spring Validator:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;

public final class SignupSpringValidator
        implements org.springframework.validation.Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "name", "name.required");

        if (form.getAge() < 18) {
            errors.rejectValue("age", "age.tooYoung");
        }
    }
}
```

Đây là mã minh họa dựa trên `SignupForm` có `getAge()`, không phải toàn bộ chương trình độc lập. `supports` phải đúng kiểu; nếu target khác kiểu, đoạn cast có thể lỗi. Có thể dùng `SignupForm.class.equals(type)` để chỉ hỗ trợ đúng lớp, hoặc `isAssignableFrom` để hỗ trợ subclass.

Spring Validator thích hợp khi quy tắc cần xét nhiều thuộc tính cùng lúc và cần chọn field nào nhận lỗi. Khi kiểm tra object lồng nhau, Spring hỗ trợ `ValidationUtils.invokeValidator(...)` và `errors.pushNestedPath(...)`/`popNestedPath()` để giữ đúng field path; không nên tự ghép path sai.

Từ Spring 6.1, interface Spring Validator còn có phương thức mặc định `validateObject(Object)` giúp validate trực tiếp và nhận `Errors`; song phương thức `validate(Object, Errors)` vẫn là hợp đồng chính trong binding.

### `SmartValidator` và validation hints

`org.springframework.validation.SmartValidator` **mở rộng Spring Validator**:

```java
void validate(Object target, Errors errors, Object... validationHints);
```

Trong adapter Bean Validation, hints có thể là các nhóm Jakarta. Spring `@Validated` hỗ trợ khai báo validation groups/hints. Do đó không chính xác khi nói “Spring tuyệt đối không có groups”: interface Spring cơ bản không có, nhưng `SmartValidator` và lớp tích hợp Jakarta có hỗ trợ.

Một custom Spring Validator chỉ chứa logic Java **không tự động hiểu** các annotation `@NotBlank`, `@Min`, hoặc các Jakarta groups nếu không có adapter/provider thích hợp.

## 5. Kết nối hai thế giới bằng `LocalValidatorFactoryBean`

`org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` là adapter trung tâm của Spring Framework 6.x cho Jakarta Bean Validation. Nó bootstrap Jakarta `ValidatorFactory`, dùng provider như Hibernate Validator, và cho phép cùng một instance được nhìn qua:

- `jakarta.validation.Validator`: trả `Set<ConstraintViolation<T>>`.
- `org.springframework.validation.SmartValidator`: ghi `Errors`/`BindingResult`, nhận hints.
- `jakarta.validation.ValidatorFactory`: truy cập factory khi cần.

Luồng xử lý khi được gọi theo Spring API:

```text
Bean có @NotBlank, @Min, custom Jakarta constraints
                       |
                       v
              Jakarta provider
                       |
                       v
             ConstraintViolation
                       |
                       v
           LocalValidatorFactoryBean
                       |
                       v
             Errors / BindingResult
            FieldError / ObjectError
```

Adapter chuyển lỗi Jakarta sang cơ chế lỗi của Spring. Nó **không tự biến** custom `org.springframework.validation.Validator` của bạn thành constraint Jakarta: một quy tắc chỉ viết trong Spring `validate(...)` sẽ không xuất hiện nếu bạn chỉ gọi Jakarta `validate(obj)`.

Trong Spring MVC, khi Bean Validation provider hiện diện, Spring thường đăng ký `LocalValidatorFactoryBean` làm validator toàn cục cho `@Valid`/`@Validated`. Spring Boot có `spring-boot-starter-validation` để bổ sung provider và cấu hình liên quan. Đừng tạo bean trùng nếu auto-configuration đã cung cấp một instance phù hợp.

## 6. Java 17 chạy độc lập: ba nhánh cùng kiểm tra một object

Ví dụ chạy đầy đủ dưới đây không khởi động web server. Nó kiểm tra `Signup("  ", 16)`, nên cả hai field đều vi phạm. Ba nhánh minh họa Jakarta API, custom Spring API, và Jakarta-to-Spring adapter.

Tạo dự án:

```text
validator-apis/
├── settings.gradle
├── build.gradle
└── src/main/java/ValidatorApisDemo.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'validator-apis'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'application'
}
repositories {
    mavenCentral()
}
dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.hibernate.validator:hibernate-validator:8.0.6.Final'
    implementation 'org.glassfish.expressly:expressly:5.0.0'
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
application {
    mainClass = 'ValidatorApisDemo'
}
```

Các version được cố định để dễ tái hiện. Trong dự án Spring Boot thật, hãy để BOM của Boot quản lý phiên bản Spring/Hibernate phù hợp. `hibernate-validator` cung cấp implementation của Jakarta Validation; `expressly` cung cấp Expression Language cho message interpolation.

**`src/main/java/ValidatorApisDemo.java`:**

```java
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

public class ValidatorApisDemo {

    public static final class Signup {

        @NotBlank(message = "name.required")
        private final String name;

        @Min(value = 18, message = "age.tooYoung")
        private final int age;

        public Signup(String name, int age) {
            this.name = name;
            this.age = age;
        }

        public String getName() {
            return name;
        }

        public int getAge() {
            return age;
        }
    }

    public static final class SignupSpringValidator
            implements org.springframework.validation.Validator {

        @Override
        public boolean supports(Class<?> type) {
            return Signup.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Signup signup = (Signup) target;
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "name", "name.required");

            if (signup.getAge() < 18) {
                errors.rejectValue("age", "age.tooYoung");
            }
        }
    }

    static String jakartaFields(
            Set<? extends ConstraintViolation<?>> violations) {
        return violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(","));
    }

    static String springFields(Errors errors) {
        return errors.getFieldErrors().stream()
                .map(FieldError::getField)
                .sorted()
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        Signup input = new Signup("  ", 16);

        // Demo Java độc lập: chủ động khởi tạo và đóng factory.
        LocalValidatorFactoryBean adapter = new LocalValidatorFactoryBean();
        adapter.afterPropertiesSet();

        try {
            // 1. Jakarta API trả violations.
            jakarta.validation.Validator jakarta = adapter;
            Set<ConstraintViolation<Signup>> violations =
                    jakarta.validate(input);
            System.out.printf("Jakarta: %d -> %s%n",
                    violations.size(), jakartaFields(violations));

            // 2. Custom Spring API ghi Errors.
            org.springframework.validation.Validator customSpring =
                    new SignupSpringValidator();
            Errors springErrors =
                    new BeanPropertyBindingResult(input, "signup");
            customSpring.validate(input, springErrors);
            System.out.printf("Spring: %d -> %s%n",
                    springErrors.getErrorCount(),
                    springFields(springErrors));

            // 3. Cùng adapter được nhìn qua Spring Validator.
            org.springframework.validation.Validator bridge = adapter;
            Errors adapterErrors =
                    new BeanPropertyBindingResult(input, "signup");
            bridge.validate(input, adapterErrors);
            System.out.printf("Adapter: %d -> %s%n",
                    adapterErrors.getErrorCount(),
                    springFields(adapterErrors));
        } finally {
            adapter.destroy();
        }
    }
}
```

Chạy ở thư mục gốc dự án bằng Java 17 và Gradle:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper thì dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows.

**Standard output kỳ vọng:**

```text
Jakarta: 2 -> age,name
Spring: 2 -> age,name
Adapter: 2 -> age,name
```

Giải thích:

1. `@NotBlank` từ chối `"  "`, `@Min(18)` từ chối 16 nên Jakarta nhận 2 violations.
2. Custom Spring Validator kiểm tra hai điều kiện tương ứng và ghi 2 `FieldError` vào `Errors`.
3. Adapter đưa hai Jakarta violations vào một `BeanPropertyBindingResult` mới, cũng có 2 field errors.
4. Vì `Set` không bảo đảm thứ tự, ví dụ **sắp xếp field names** trước khi in để stdout ổn định.
5. Vì không có Spring container trong demo, `afterPropertiesSet()` và `destroy()` được gọi tường minh. Trong Spring ApplicationContext, container quản lý lifecycle.

Demo dùng object immutable có getter để minh họa validation trực tiếp. Khi nhận HTML form qua `@ModelAttribute`, cần model và chiến lược data binding phù hợp; ví dụ không tự chứng minh HTTP binding.

## 7. Spring MVC: `@Valid`, `@Validated`, `BindingResult`

Trong ứng dụng Spring MVC có Bean Validation provider và cấu hình validator phù hợp, đặt Jakarta `@Valid` hoặc Spring `@Validated` trên model argument để yêu cầu kiểm tra sau bước binding.

Ví dụ minh họa **method bên trong `@Controller`**, giả định `SignupForm` là model có getter/setter hoặc cơ chế binding phù hợp, và có view tương ứng:

```java
import jakarta.validation.Valid;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@PostMapping("/signup")
public String submit(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "signup-form";
    }
    return "signup-success";
}
```

`BindingResult` **phải đứng ngay sau** tham số mà nó biểu diễn lỗi nếu controller muốn xử lý trực tiếp các lỗi binding/validation ấy.

Để đăng ký một custom Spring Validator cục bộ cho model `signup`, đặt phương thức sau **bên trong controller**:

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("signup")
public void initBinder(WebDataBinder binder) {
    binder.addValidators(new SignupSpringValidator());
}
```

`SignupSpringValidator.supports(...)` phải hỗ trợ kiểu model. Khi có validator Jakarta toàn cục, `addValidators` có thể làm cả validator Jakarta và custom validator cùng chạy. Nếu cùng một rule được viết hai lần, lỗi field có thể bị trùng; nên giao mỗi rule cho một nơi chịu trách nhiệm.

Muốn chọn Jakarta validation group, có thể dùng Spring `@Validated`:

```java
@Validated(PublishChecks.class)
@ModelAttribute("signup") SignupForm form
```

Đây là **đoạn khai báo tham số**, không phải phương thức controller hoàn chỉnh. `@Validated` cho phép chỉ định groups/hints; `@Valid` theo Jakarta không trực tiếp mang một danh sách group như vậy.

Lưu ý Spring MVC 6.1+ còn có **method validation** khi constraint đặt trực tiếp trên tham số hoặc return value. Xử lý lỗi có thể đi theo `MethodArgumentNotValidException` hoặc `HandlerMethodValidationException` tùy chữ ký và tình huống. Không mặc định mọi lỗi `@Valid` đều cùng một exception type.

`@RequestBody` được Jackson/`HttpMessageConverter` giải mã trước khi constraint validation trên object được thực hiện. JSON sai cú pháp hoặc sai kiểu là vấn đề deserialize/binding, không đồng nghĩa `ConstraintViolation`. Cần xử lý đúng các nhóm lỗi và định nghĩa DTO lỗi HTTP, không đưa giá trị nhạy cảm từ `getInvalidValue()` vào response.

## 8. Chọn hướng triển khai

| Nhu cầu | API phù hợp | Giải thích |
| --- | --- | --- |
| Field bắt buộc, giới hạn độ dài, khoảng số, pattern phổ biến | Jakarta constraints | Ngắn gọn, tái sử dụng qua nhiều tầng |
| Custom constraint tái sử dụng và có groups | Jakarta `@Constraint` + `ConstraintValidator` | Tận dụng standard metadata/cascade/groups |
| Quy tắc liên quan nhiều field trong một form cụ thể | Spring Validator | Chủ động chọn lỗi field hay object, error codes |
| Dùng Jakarta constraint trong Spring form binding | `LocalValidatorFactoryBean`/`SmartValidator` | Chuyển violations thành `Errors` |
| Service/batch cần validation độc lập HTTP | Jakarta Validator | Nhận tập violations có cấu trúc |
| Form có bước Create/Update/Publish | Jakarta groups; Spring `@Validated` | Kích hoạt đúng tập constraint |
| Ràng buộc uniqueness khi nhiều request đồng thời | Service + DB constraint/transaction | Validation trước khi ghi không loại bỏ race condition |

Có thể kết hợp cả Jakarta và Spring validator. Tuy nhiên, tránh viết cùng quy tắc ở nhiều chỗ và tránh giả định adapter sẽ tự chuyển rule Spring sang provider Jakarta.

## 9. Lỗi phổ biến cần tránh

1. **Nhầm package:** Jakarta `Validator` không có `supports(Class<?>)`; Spring `Validator` không trả `Set<ConstraintViolation>`.
2. **Thiếu provider:** chỉ thêm `jakarta.validation-api` không đủ để chạy annotation constraint.
3. **Bỏ qua kết quả:** Jakarta `validate(...)` trả `Set`; Spring `validate(...)` ghi vào `Errors`, không tự ném exception vì input sai.
4. **Sai `supports`:** validator được gắn vào model không thuộc kiểu hỗ trợ; có thể dẫn đến lỗi binder hoặc lỗi cast.
5. **Trùng lỗi:** vừa `@Min` vừa custom Spring validator cùng kiểm tra tuổi ở một flow.
6. **Nhầm groups:** chạy nhóm riêng không có nghĩa mọi constraint trong nhóm `Default` cũng được chạy.
7. **Quên cascade:** `@NotNull` của parent không có nghĩa constraints bên trong child cũng được validate.
8. **Nhầm code/message:** `FieldError.getCode()` dùng với Spring message resolution; `ConstraintViolation.getMessage()` là message Jakarta đã nội suy.
9. **Sai giả định về adapter:** custom Spring rule không tự hiện ra trong `jakartaValidator.validate(...)`.
10. **Xem validation là hàng rào DB:** uniqueness và toàn vẹn dữ liệu cần kiểm soát ở tầng lưu trữ.
11. **Trộn `javax.validation` với `jakarta.validation`:** Spring Framework 6+/Spring Boot 3+ dùng Jakarta namespace.
12. **Cho rằng mọi lỗi request đều từ Bean Validation:** phải phân biệt JSON parsing, type conversion, form binding, object constraint và method validation.
13. **Dựa vào thứ tự `ConstraintViolation` Set:** sắp xếp khi test hoặc hiển thị.
14. **Đưa invalid value nhạy cảm ra log/HTTP:** chỉ trả code, path, message phù hợp.

## 10. Tự kiểm tra và bài tập

### Câu hỏi

- Jakarta `validate(form)` trả gì? **`Set<ConstraintViolation<Form>>`, rỗng nếu không có violation trong groups được xét.**
- Spring `validate(form, errors)` trả gì? **`void`; lỗi được thêm vào `errors`.**
- `LocalValidatorFactoryBean` có thể dùng dưới cả hai interface không? **Có, khi được cấu hình với provider.**
- Một custom Spring Validator có khiến Jakarta API tự nhận các rule Java của nó không? **Không.**
- Vì sao thêm `@Valid` ở field lồng nhau? **Để yêu cầu cascade validation vào object con.**
- Khi nào dùng `@Validated`? **Khi cần nhóm/hints trong ngữ cảnh Spring hỗ trợ.**

### Bài tập thực hành

1. Thay `new Signup("  ", 16)` thành `new Signup("Mai", 22)`: cả ba nhánh nên có **0 lỗi**.
2. Thay thành `new Signup("Mai", 16)`: cả ba nhánh chỉ có lỗi field **`age`**.
3. Thêm `confirmPassword` và kiểm tra bằng Spring `Errors`; so sánh cách viết Jakarta class-level constraint.
4. Tạo nhóm `PublishChecks`; chỉ định một constraint thuộc nhóm ấy và so sánh kết quả với `Default`.
5. Thêm một endpoint MVC nhận `@Valid @ModelAttribute`, rồi kiểm tra tình huống sai constraint và sai kiểu dữ liệu để phân biệt hai nhóm lỗi.

## 11. Tài liệu chính thức

- [Spring Framework — Validation Using Spring’s Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html): `supports`, `validate`, `Errors`, `ValidationUtils`.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Jakarta provider, `LocalValidatorFactoryBean`, hai interface.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, `@Validated`, method validation.
- [Jakarta Bean Validation — Validator API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html): `validate`, `validateProperty`, `validateValue`, groups.
- [Spring Framework 6.2 — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html): adapter và lifecycle.
- [Hibernate Validator — 8.0 series](https://hibernate.org/validator/releases/8.0/): provider được dùng trong ví dụ.

**Kết luận kiến thức:** hai `Validator` giải quyết cùng nhu cầu kiểm tra dữ liệu qua hai hợp đồng khác nhau. Jakarta mô tả constraint và trả `ConstraintViolation`; Spring Validator ghi lỗi vào `Errors`. `LocalValidatorFactoryBean` cho phép Jakarta constraint tham gia luồng binding và validation của Spring MVC.

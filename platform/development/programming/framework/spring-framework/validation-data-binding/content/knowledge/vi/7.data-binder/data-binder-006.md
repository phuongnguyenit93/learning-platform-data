# DataBinder: setValidator, addValidators và replaceValidators

Trong Spring Framework, **`DataBinder`** quản lý việc gắn giá trị vào một đối tượng và có thể chạy các **`Validator`** để kiểm tra đối tượng ấy. Khi một form hoặc API có nhiều nhóm quy tắc — ví dụ kiểm tra trường bắt buộc, tuổi hợp lệ và quy tắc nghiệp vụ — ba phương thức **`setValidator(...)`**, **`addValidators(...)`** và **`replaceValidators(...)`** quyết định **validator nào được đăng ký trong binder, thứ tự của chúng và việc một danh sách cũ có được giữ lại hay không**.

Điều cần phân biệt ngay từ đầu: **đăng ký validator không đồng nghĩa với chạy validation**. Khi sử dụng `DataBinder` trực tiếp, ta gọi `binder.validate()` để thực thi. Trong Spring MVC, sau data binding, các annotation như `@Valid` hoặc `@Validated` trên tham số phù hợp có thể kích hoạt quá trình validation theo cơ chế của Spring MVC.

Bài này tập trung vào API của `org.springframework.validation.DataBinder`, cách phối hợp nhiều Spring `Validator`, cách đọc `BindingResult` và ảnh hưởng của ba phương thức này trong `WebDataBinder`.

## 1. DataBinder, Validator và BindingResult nằm ở đâu trong luồng?

```text
Đối tượng đích (target) + dữ liệu đầu vào
             |
             v
          DataBinder
             |
             +-- bind(PropertyValues)
             |      chuyển kiểu và ghi property
             |
             +-- danh sách Validator đã đăng ký
             |      setValidator / addValidators / replaceValidators
             |
             +-- validate() khi được gọi
                    |
                    +-- Validator 1
                    +-- Validator 2
                    +-- ...
                    |
                    v
              BindingResult
             (field errors, global errors)
```

Các thành phần:

| API | Chức năng |
| --- | --- |
| `DataBinder` | Gắn giá trị vào object; lưu cấu hình chuyển kiểu, các quy tắc binding và các validator |
| `Validator` | Giao diện của Spring có `supports(Class<?>)` và `validate(Object, Errors)` |
| `SmartValidator` | Mở rộng `Validator` để hỗ trợ validation hints khi được truyền |
| `Errors` | Đối tượng mà validator dùng để ghi lỗi field/object |
| `BindingResult` | Mở rộng `Errors`, chứa cả lỗi binding và validation |
| `WebDataBinder` | Biến thể `DataBinder` cho môi trường web, thường được Spring MVC cấu hình qua `@InitBinder` |

Ví dụ một `Validator` đơn giản:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class AgeValidator implements Validator {
    @Override
    public boolean supports(Class<?> type) {
        return RegistrationForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationForm form = (RegistrationForm) target;
        if (form.getAge() != null && form.getAge() < 18) {
            errors.rejectValue("age", "age.tooYoung");
        }
    }
}
```

Đây là **đoạn minh họa**, giả định có `RegistrationForm` với `getAge()`; mã chạy độc lập đầy đủ sẽ được cung cấp ở phần 5. `supports(...)` mô tả kiểu đối tượng phù hợp; `validate(...)` đọc target và thêm lỗi vào `Errors` khi quy tắc không thỏa.

**Lưu ý tên kiểu:** `org.springframework.validation.Validator` khác `jakarta.validation.Validator`. Ba phương thức của `DataBinder` đang bàn dùng giao diện Validator của **Spring**. Spring có adapter như `LocalValidatorFactoryBean` để tích hợp Jakarta Bean Validation với cơ chế này.

## 2. So sánh chính xác ba phương thức

Giả sử đang có danh sách validator trong một `DataBinder`:

```text
[A, B]
```

Trong đó A, B và C là các instance `org.springframework.validation.Validator`.

| Lệnh | Danh sách sau lệnh | Diễn giải |
| --- | --- | --- |
| `binder.setValidator(C)` | `[C]` | Xóa danh sách cũ rồi đặt một validator |
| `binder.addValidators(C)` | `[A, B, C]` | Nối thêm validator vào danh sách |
| `binder.replaceValidators(C, A)` | `[C, A]` | Xóa danh sách cũ rồi thay bằng nhiều validator truyền vào |
| `binder.setValidator(null)` | `[]` | Xóa danh sách validator đã cấu hình |
| `binder.replaceValidators()` | `[]` | Thay bằng danh sách rỗng |

**`setValidator(Validator validator)`** mang ý nghĩa đặt một validator duy nhất cho binder. Nó không chỉ thay phần tử đầu mà **xóa toàn bộ validator đã có** trước khi thêm validator mới (nếu đối số khác `null`). Vì vậy, sau khi cấu hình thêm nhiều validator, gọi `setValidator(...)` lần nữa có thể làm mất những validator đang được sử dụng.

**`addValidators(Validator... validators)`** nhận một hoặc nhiều validator và **bổ sung** vào danh sách đang có. Đây là lựa chọn thường dùng khi cần giữ validator mặc định hoặc validator được cấu hình trước đó rồi thêm quy tắc riêng của module/controller.

**`replaceValidators(Validator... validators)`** thay **toàn bộ danh sách** bằng các validator được truyền vào theo đúng thứ tự. Nó thích hợp khi muốn chủ động kiểm soát đầy đủ tập validator và có thể cần nhiều hơn một validator mới. Gọi với không có đối số sẽ tạo danh sách rỗng.

Cả ba thao tác là **cấu hình**. Chúng không tự kiểm tra lại dữ liệu, không xóa lỗi đã có trong `BindingResult` và không tự chạy `validate()`.

### Thứ tự đăng ký có ý nghĩa

Giả sử:

```java
binder.setValidator(nameValidator);
binder.addValidators(ageValidator, emailValidator);
```

Danh sách là:

```text
[nameValidator, ageValidator, emailValidator]
```

Khi gọi `binder.validate()`, các validator được áp dụng theo thứ tự của danh sách (trừ validator bị loại bằng cơ chế cấu hình lọc, nếu có). Nếu một validator ghi lỗi, lỗi đó **không mặc nhiên ngăn những validator kế tiếp chạy**. Do đó cần tránh giả định một validator sẽ "short circuit" các validator khác. Các quy tắc nên độc lập hoặc xử lý an toàn khi giá trị không hợp lệ.

Khi cần thay thứ tự, có thể dùng:

```java
binder.replaceValidators(emailValidator, nameValidator, ageValidator);
```

Việc thay đổi thứ tự có thể ảnh hưởng thứ tự lỗi và các validator phụ thuộc vào trạng thái đã được kiểm tra trước đó; tốt nhất viết validator không phụ thuộc vào hiệu ứng phụ của validator khác.

## 3. getValidator(), getValidators() và getValidatorsToApply()

Cấu hình nhiều validator khiến một số API dễ bị hiểu nhầm.

| API | Giá trị trả về |
| --- | --- |
| `binder.getValidator()` | Validator **đầu tiên** trong danh sách, hoặc `null` nếu không có |
| `binder.getValidators()` | Danh sách validator đã cấu hình, không cho phép sửa trực tiếp |
| `binder.getValidatorsToApply()` | Các validator sẽ được áp dụng sau khi xét predicate loại trừ, nếu đã cấu hình; có từ Spring 6.1 |

Ví dụ:

```java
binder.setValidator(nameValidator);
binder.addValidators(ageValidator);
System.out.println(binder.getValidator() == nameValidator); // true
System.out.println(binder.getValidators().size());          // 2
```

**`getValidator()` chỉ trả về validator đầu tiên**, không có nghĩa chỉ validator đầu tiên được chạy. Muốn xem toàn bộ tập đã đăng ký, dùng `getValidators()`. Ở Spring 6.1+, `setExcludedValidators(Predicate<Validator>)` cho phép loại một số validator khỏi tập thực thi; khi cần biết tập đang được áp dụng, `getValidatorsToApply()` là phương thức thích hợp.

Đừng sửa danh sách trả về từ `getValidators()` bằng `add(...)` hoặc `clear()`; kết quả trả về được bảo vệ khỏi sửa đổi trực tiếp. Hãy dùng đúng ba phương thức cấu hình thay vì can thiệp danh sách nội bộ.

## 4. Kiểm tra kiểu target và phạm vi hỗ trợ

Khi binder đã có object đích, Spring kiểm tra validator được đăng ký có hỗ trợ class của object đó hay không thông qua `supports(Class<?>)`. Nếu validator không hỗ trợ target, thao tác đăng ký có thể ném **`IllegalStateException`** với thông tin kiểu/validator không phù hợp.

```java
@Override
public boolean supports(Class<?> type) {
    return RegistrationForm.class.isAssignableFrom(type);
}
```

Cách viết bằng `isAssignableFrom` cho phép hỗ trợ `RegistrationForm` và những subclass phù hợp. Việc viết:

```java
return type == RegistrationForm.class;
```

chỉ chấp nhận chính class đó. Cả hai có thể đúng tùy chủ đích, nhưng phải thống nhất với kiểu object thực tế của binder.

Đối với validator chỉ xử lý `Address`, đừng đăng ký trực tiếp vào `DataBinder` có target là `RegistrationForm` trừ khi validator đó thật sự hỗ trợ `RegistrationForm`. Thay vào đó, cho validator của form gọi validator con cho `Address` và dùng `Errors.pushNestedPath("address")`/`popNestedPath()` nếu cần gắn tên lỗi con. Cách kiểm tra của `DataBinder` ở đây là **kiểu của target ở cấp binder**, không phải việc nó chứa những field có kiểu nào.

Lưu ý thêm: một `Validator` dùng chung nên tránh giữ mutable state riêng của từng request. Trạng thái lỗi và dữ liệu input thuộc về `Errors`/`BindingResult` và target của từng lần kiểm tra.

## 5. Ví dụ Java 17 chạy được: nhìn thấy hành vi của cả ba API

Ví dụ không cần web server. Nó sử dụng Spring Framework Core Validation, ba validator độc lập và **ba DataBinder khác nhau** để phân biệt chính xác hiệu ứng của từng cách cấu hình mà không tái sử dụng những lỗi đã có từ lần validate trước.

### 5.1. Cấu trúc dự án

```text
data-binder-validators/
├── settings.gradle
├── build.gradle
└── src/main/java/example/ValidatorRegistryDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'data-binder-validators'
```

**`build.gradle`**

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
}

application {
    mainClass = 'example.ValidatorRegistryDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Dùng JDK 17+ cùng Gradle phiên bản tương thích với JDK/Spring; cần truy cập Maven Central khi tải dependency lần đầu. `spring-context` mang theo những dependency Spring cần thiết cho API validation trong ví dụ.

### 5.2. Tệp Java đầy đủ

**`src/main/java/example/ValidatorRegistryDemo.java`**

```java
package example;

import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

import java.util.List;

public class ValidatorRegistryDemo {

    public static final class RegistrationForm {
        private final String name;
        private final String email;
        private final Integer age;

        public RegistrationForm(String name, String email, Integer age) {
            this.name = name;
            this.email = email;
            this.age = age;
        }

        public String getName() {
            return name;
        }

        public String getEmail() {
            return email;
        }

        public Integer getAge() {
            return age;
        }
    }

    public static final class NameValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "name", "name.required");
        }
    }

    public static final class AgeValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            RegistrationForm form = (RegistrationForm) target;
            if (form.getAge() == null || form.getAge() < 18) {
                errors.rejectValue("age", "age.invalid");
            }
        }
    }

    public static final class EmailValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return RegistrationForm.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            RegistrationForm form = (RegistrationForm) target;
            if (form.getEmail() == null
                    || !form.getEmail().contains("@")) {
                errors.rejectValue("email", "email.invalid");
            }
        }
    }

    private static List<String> validatorNames(DataBinder binder) {
        return binder.getValidators().stream()
                .map(validator -> validator.getClass().getSimpleName())
                .toList();
    }

    private static List<String> errorFields(DataBinder binder) {
        return binder.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getField)
                .toList();
    }

    public static void main(String[] args) {
        RegistrationForm form =
                new RegistrationForm("   ", "invalid-email", 16);

        Validator byName = new NameValidator();
        Validator byAge = new AgeValidator();
        Validator byEmail = new EmailValidator();

        // Trường hợp 1: set một validator, rồi add thêm một.
        DataBinder additive = new DataBinder(form, "registration");
        additive.setValidator(byName);
        additive.addValidators(byAge);
        System.out.println("setThenAdd=" + validatorNames(additive));
        additive.validate();
        System.out.println("setThenAddErrors=" + errorFields(additive));

        // Trường hợp 2: replace loại các validator trước đó.
        DataBinder replaced = new DataBinder(form, "registration");
        replaced.setValidator(byName);
        replaced.addValidators(byAge);
        replaced.replaceValidators(byEmail, byAge);
        System.out.println("replaced=" + validatorNames(replaced));
        System.out.println("primary="
                + replaced.getValidator().getClass().getSimpleName());
        replaced.validate();
        System.out.println("replacedErrors=" + errorFields(replaced));

        // Trường hợp 3: set sau add sẽ giữ lại đúng một validator.
        DataBinder reset = new DataBinder(form, "registration");
        reset.addValidators(byName, byAge);
        reset.setValidator(byEmail);
        System.out.println("setAfterAdd=" + validatorNames(reset));
    }
}
```

`RegistrationForm` ở đây là class immutable, có getter và được tạo sẵn từ constructor. Ví dụ **chỉ minh họa validation**, không thực hiện `binder.bind(...)` hay property binding. Vì vậy không cần setter. Nếu muốn bind dữ liệu form qua setter, hãy dùng một DTO mutable có các setter phù hợp hoặc cấu hình constructor binding riêng.

### 5.3. Chạy và đối chiếu stdout

Từ thư mục dự án:

```bash
gradle -q run
```

Nếu đã có Gradle wrapper trên Unix/macOS, dùng `./gradlew -q run`; trên Windows dùng `gradlew.bat -q run`.

**Stdout kỳ vọng:**

```text
setThenAdd=[NameValidator, AgeValidator]
setThenAddErrors=[name, age]
replaced=[EmailValidator, AgeValidator]
primary=EmailValidator
replacedErrors=[email, age]
setAfterAdd=[EmailValidator]
```

Giải thích theo từng dòng:

- `setThenAdd` chứa hai validator do `setValidator(byName)` rồi `addValidators(byAge)`.
- Khi chạy `additive.validate()`, `name` chỉ có khoảng trắng nên lỗi `name`; `age=16` nên lỗi `age`. Email chưa được đăng ký trong binder này.
- `replaceValidators(byEmail, byAge)` thay danh sách thành `[EmailValidator, AgeValidator]`. `NameValidator` không chạy, dù `name` vẫn là chuỗi toàn khoảng trắng.
- `getValidator()` trả về validator đầu tiên của danh sách mới, tức `EmailValidator`.
- `replacedErrors` chứa `email` và `age` theo thứ tự gọi của hai validator. `name` không nằm trong danh sách lỗi vì validator của tên đã bị thay thế.
- `setAfterAdd` chỉ chứa `EmailValidator`: `setValidator` xóa các validator được add trước đó.

Đầu ra này thể hiện **khác biệt giữa cấu hình danh sách validator và kết quả validation**. Hai binder riêng biệt giữ hai `BindingResult` khác nhau, nên không có lỗi cũ xen vào dữ liệu của ví dụ.

## 6. Chỉ đăng ký không đủ: phải kích hoạt validate đúng lúc

Ví dụ minh họa thứ tự chuẩn khi sử dụng `DataBinder` thủ công:

```java
RegistrationForm target =
        new RegistrationForm("Lan", "lan@example.org", 25);
DataBinder binder = new DataBinder(target, "registration");

binder.setValidator(new NameValidator());
binder.addValidators(new AgeValidator(), new EmailValidator());

// Đối tượng đã có dữ liệu; đây là bước thực thi validation.
binder.validate();

boolean invalid = binder.getBindingResult().hasErrors();
```

Lệnh `setValidator` và `addValidators` ở trên chỉ thay danh sách; **`binder.validate()`** mới thực thi validator và ghi lỗi. Nếu dùng mutable JavaBean và muốn chuyển dữ liệu từ request-like map trước khi validate, thứ tự khái quát là:

```java
binder.bind(new MutablePropertyValues(inputValues));
binder.validate();
BindingResult result = binder.getBindingResult();
```

Đây là **mẫu minh họa**, cần có `inputValues` và import `org.springframework.beans.MutablePropertyValues` phù hợp. `bind(...)` xử lý giá trị vào field và có thể sinh lỗi chuyển kiểu, còn `validate()` gọi validator đã đăng ký. `BindingResult` có thể chứa cả hai loại lỗi.

**Cảnh báo về tái sử dụng binder:** Nếu gọi `validate()` nhiều lần trên **cùng một `DataBinder`**, các lỗi đã được ghi trong `BindingResult` không tự động biến mất chỉ vì `setValidator(...)` hoặc `replaceValidators(...)` được gọi. Để so sánh hai danh sách validator một cách công bằng, hãy tạo binder mới với kết quả lỗi riêng, như ví dụ ở phần 5. Đừng diễn giải lỗi cũ còn tồn tại là bằng chứng validator đã bị gỡ vẫn tiếp tục chạy.

### Validation hints

Khi gọi `binder.validate(hints...)`, nếu validator thực thi `SmartValidator`, Spring có thể truyền các hints vào `validate(target, errors, hints...)`. `Validator` thông thường chỉ có `validate(target, errors)`, nên không tự có cơ chế xử lý group/hint. Muốn áp dụng Jakarta Bean Validation groups, hãy hiểu adapter và `@Validated` đang tham gia; **các phương thức set/add/replace không tự định nghĩa group**.

## 7. Tác động thực tế trong Spring MVC và @InitBinder

Trong Spring MVC, `WebDataBinder` mở rộng `DataBinder`. Controller có thể cấu hình binder dành cho một model attribute qua `@InitBinder`:

```java
@Controller
@RequestMapping("/registrations")
public class RegistrationController {

    private final RegistrationBusinessValidator businessValidator;

    public RegistrationController(
            RegistrationBusinessValidator businessValidator) {
        this.businessValidator = businessValidator;
    }

    @InitBinder("registrationForm")
    void configureRegistration(WebDataBinder binder) {
        binder.addValidators(businessValidator);
    }

    @PostMapping
    String submit(
            @Valid @ModelAttribute("registrationForm")
            RegistrationForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return "registration/form";
        }
        return "registration/success";
    }
}
```

Đây là **mã minh họa tích hợp**, cần import Spring MVC, `@Valid`, `WebDataBinder` và có class `RegistrationBusinessValidator` hỗ trợ `RegistrationForm` cũng như view/ứng dụng tương ứng. Không thể chạy riêng đoạn này bằng `javac` nếu không có các dependency và class phụ trợ. Nó cho thấy vị trí đúng để thêm validator cục bộ; `@InitBinder("registrationForm")` giới hạn callback cho model attribute tên `registrationForm`.

Trong ứng dụng Spring MVC có Jakarta Bean Validation provider, Spring thường cấu hình một validator toàn cục (chẳng hạn `LocalValidatorFactoryBean`) cho `@Valid` hoặc `@Validated`. Khi muốn **bổ sung** quy tắc riêng của form mà vẫn dùng các constraint như `@NotBlank`, `@Email`, `@Min`:

```java
@InitBinder("registrationForm")
void configure(WebDataBinder binder) {
    binder.addValidators(new RegistrationBusinessValidator());
}
```

`addValidators` thường phù hợp vì giữ các validator đã có. Ngược lại:

```java
@InitBinder("registrationForm")
void configure(WebDataBinder binder) {
    binder.setValidator(new RegistrationBusinessValidator());
}
```

làm danh sách chỉ còn validator được chỉ định, **có thể thay thế cả validator Bean Validation toàn cục** đã được Spring MVC gắn vào binder. Khi đó, đừng mặc định các annotation Jakarta Validation vẫn được chạy qua validator trước đây.

Nếu yêu cầu là thay thế có chủ đích toàn bộ các validator:

```java
@InitBinder("registrationForm")
void configure(WebDataBinder binder) {
    binder.replaceValidators(
            new RegistrationBusinessValidator(),
            new RegistrationCrossFieldValidator());
}
```

Đoạn này giả định cả hai validator hỗ trợ kiểu `RegistrationForm`. `replaceValidators` mô tả chính xác ý đồ dùng **bộ validator mới**, trong khi `addValidators` mô tả ý đồ **bổ sung**.

**Cần xác định cơ chế kích hoạt:** `@Valid`/`@Validated` trên tham số model phù hợp có thể khiến Spring MVC gọi validator sau binding. Việc tự cấu hình `@InitBinder` không phải thao tác validate ngay trong callback; `@InitBinder` chủ yếu chuẩn bị binder cho quá trình xử lý request.

## 8. Kịch bản chọn phương thức theo mục tiêu

| Mục tiêu | Nên cân nhắc | Lý do |
| --- | --- | --- |
| Chỉ có một validator, muốn đặt rõ danh sách còn đúng một | `setValidator(v)` | Xóa mọi validator trước đó rồi đặt `v` |
| Duy trì Bean Validation toàn cục và thêm rule nghiệp vụ trong controller | `addValidators(v)` | Giữ cấu hình trước |
| Muốn bổ sung hai rule riêng theo thứ tự | `addValidators(v1, v2)` | Nối thêm các validator theo thứ tự |
| Muốn chủ động thay toàn bộ bộ kiểm tra hiện có bằng hai validator | `replaceValidators(v1, v2)` | Danh sách kết quả chính xác là `[v1, v2]` |
| Muốn xóa hết danh sách đã đăng ký | `replaceValidators()` hoặc `setValidator(null)` | Cả hai đưa danh sách về rỗng |
| Muốn xem validator đầu tiên | `getValidator()` | Trả phần tử đầu, có thể là `null` |
| Muốn kiểm tra tất cả validator đã cấu hình | `getValidators()` | Trả danh sách đầy đủ |
| Muốn so kết quả lỗi của hai bộ validator | Tạo hai binder riêng | Tránh việc lỗi cũ vẫn tồn tại trong cùng `BindingResult` |

Đôi khi cần chọn bộ kiểm tra riêng theo workflow (ví dụ tạo mới hoặc cập nhật). Thay vì sửa danh sách tùy tiện trong khi đang validate, nên cấu hình binder rõ ràng trước khi chạy và dùng validator phù hợp với target. Nếu các quy tắc chỉ khác theo nhóm Bean Validation, cân nhắc dùng `@Validated(Group.class)` hoặc `SmartValidator` phù hợp, không nhất thiết thay toàn bộ validator.

## 9. Lỗi thường gặp

### 9.1. Nhầm `setValidator` với `addValidators`

```java
binder.addValidators(requiredFieldsValidator);
binder.setValidator(businessValidator);
```

Sau hai dòng trên, danh sách chỉ còn `businessValidator`. Nếu muốn chạy cả hai, phải dùng:

```java
binder.addValidators(requiredFieldsValidator);
binder.addValidators(businessValidator);
```

hoặc chỉ định toàn bộ danh sách bằng `replaceValidators(requiredFieldsValidator, businessValidator)`.

### 9.2. Chỉ nhìn `getValidator()` rồi tưởng chỉ có một validator

```java
binder.setValidator(first);
binder.addValidators(second);
System.out.println(binder.getValidator() == first); // true
```

Dòng trên không phủ nhận sự hiện diện của `second`. Hãy xem `getValidators()` để biết danh sách cấu hình.

### 9.3. Không gọi validate sau khi cấu hình thủ công

```java
DataBinder binder = new DataBinder(target);
binder.addValidators(customValidator);
// Nếu không gọi binder.validate(), customValidator chưa được thực thi.
```

Đây là lý do object có thể chứa dữ liệu sai nhưng `BindingResult` chưa có lỗi validator; hãy kiểm tra luồng thực thi, không chỉ xem cấu hình.

### 9.4. Validator không hỗ trợ kiểu target

```java
@Override
public boolean supports(Class<?> type) {
    return Address.class.isAssignableFrom(type);
}
```

Một validator chỉ hỗ trợ `Address` thường không thể đăng ký cho binder có target `RegistrationForm` nếu `RegistrationForm` không phải subtype `Address`. Giải pháp là tạo validator cha cho `RegistrationForm` và gọi validator của `Address` đúng ngữ cảnh, hoặc thiết kế lại validator để `supports` mô tả đúng target.

### 9.5. Đăng ký lặp cùng validator

`addValidators` là thao tác nối danh sách, không phải cơ chế đảm bảo chỉ có một instance theo kiểu. Nếu cùng validator được thêm nhiều lần, nó có thể được chạy nhiều lần và ghi lỗi trùng. Trước khi gọi `addValidators` trong nhiều điểm cấu hình, hãy xác định ai chịu trách nhiệm đăng ký và kiểm tra danh sách thực tế.

### 9.6. Tưởng replace xóa các lỗi đã có

`replaceValidators(...)` đổi danh sách **validator cho lần validate tiếp theo**, không phải API xóa lỗi trong `BindingResult`. Kết quả lỗi đã tạo trước đó vẫn có thể nằm trong binder, nên không dùng cùng binder để so sánh các cấu hình mà không kiểm soát lịch sử validation.

### 9.7. Nhầm Spring Validator với Jakarta Validator

`jakarta.validation.Validator` không phải kiểu đầu vào trực tiếp của `DataBinder.addValidators(...)`. Khi cần Jakarta Validation, dùng tích hợp Spring phù hợp (ví dụ adapter `LocalValidatorFactoryBean`), không ép kiểu hai interface khác nhau. Khi có `@Valid`/`@Validated`, hãy xem các validator đã được Spring MVC đăng ký.

### 9.8. Validation không phải bộ lọc field được bind

Bất kể có bao nhiêu validator, việc client có thể thay đổi một thuộc tính không được giải quyết chỉ bằng validation. Khi bind input từ request, ưu tiên DTO chứa các trường được phép nhận, dùng `setAllowedFields(...)` hoặc cơ chế binding phù hợp, tránh *mass assignment* vào domain entity chứa field nhạy cảm như `role` hoặc `approved`.

## 10. Cách tự kiểm chứng trong code và test

Với một binder có target hợp lệ, có thể kiểm tra các bất biến:

1. Sau `setValidator(a)`, `getValidators()` có đúng `[a]`.
2. Sau `addValidators(b, c)`, danh sách thành `[a, b, c]`, giữ nguyên thứ tự.
3. Sau `replaceValidators(c, b)`, danh sách còn `[c, b]`.
4. `getValidator()` là `c`, validator đứng đầu.
5. Sau `binder.validate()`, lỗi ghi bởi `c` và `b` xuất hiện; lỗi chỉ do `a` tạo không xuất hiện **nếu chưa từng validate bằng `a` trước đó**.
6. `setValidator(null)` hoặc `replaceValidators()` khiến `getValidators()` rỗng.
7. Nếu validator không `supports(target.getClass())`, việc thêm validator phải bị từ chối, thay vì chấp nhận một quy tắc cho sai class.

Đoạn kiểm tra sau dùng giả định `a`, `b`, `c` đều là validator hỗ trợ target:

```java
DataBinder binder = new DataBinder(target, "form");
binder.setValidator(a);
binder.addValidators(b);
assert binder.getValidators().size() == 2;
assert binder.getValidator() == a;

binder.replaceValidators(c, b);
assert binder.getValidators().size() == 2;
assert binder.getValidator() == c;
```

Đây là **đoạn minh họa** bên trong test hoặc method có sẵn các biến. Java assertion bị tắt theo mặc định; khi dùng `assert`, bật `-ea` cho JVM hoặc dùng assertion của JUnit/AssertJ.

Trong unit test, nên tạo target/binder mới cho mỗi kịch bản. Khi test Spring MVC, kiểm tra cả **lỗi field** lẫn việc cấu hình validator địa phương có vô tình thay thế Bean Validation toàn cục hay không; đây là nơi `addValidators` và `setValidator` thường gây khác biệt thực tế.

## 11. Ghi nhớ

- **`setValidator(v)`**: cấu hình còn một validator `v`; validator cũ bị loại.
- **`addValidators(v1, v2)`**: nối thêm `v1`, `v2` vào danh sách hiện tại.
- **`replaceValidators(v1, v2)`**: thay toàn bộ danh sách bằng `v1`, `v2`.
- **`getValidator()`**: trả về validator đầu tiên; **`getValidators()`**: trả về cả danh sách.
- **`binder.validate()`**: thực thi các validator đã cấu hình; thông tin lỗi được thu thập trong **`BindingResult`**.
- **Trong `@InitBinder`**, dùng `addValidators` khi cần giữ validator toàn cục và bổ sung logic riêng. Dùng `setValidator` hoặc `replaceValidators` khi chủ động muốn thay thế.

### Bài tập tự luyện

Bạn có ba validator: `RequiredValidator`, `CrossFieldValidator` và `BusinessValidator`. Một `DataBinder` đã có `RequiredValidator`. Hãy dự đoán danh sách sau từng lệnh:

```java
binder.addValidators(crossFieldValidator);
binder.setValidator(businessValidator);
binder.addValidators(requiredValidator);
binder.replaceValidators(
        crossFieldValidator, requiredValidator);
```

**Đáp án:** sau add đầu là `[RequiredValidator, CrossFieldValidator]`; sau set là `[BusinessValidator]`; sau add tiếp là `[BusinessValidator, RequiredValidator]`; sau replace cuối là `[CrossFieldValidator, RequiredValidator]`. `BusinessValidator` không còn trong danh sách. Điều này chỉ nói về cấu hình; lỗi chỉ phát sinh khi validation được kích hoạt.

## Tài liệu chính thức

- [Spring Framework — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/validation/DataBinder.html): ba phương thức đăng ký validator, truy vấn danh sách và thực thi validation.
- [Spring Framework — Validation qua Spring Validator](https://docs.spring.io/spring-framework/reference/core/validation/validator.html): giao diện `Validator`, kiểm tra kiểu và ghi lỗi.
- [Spring Framework — Bean Validation Integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): cấu hình `DataBinder` và cách kết hợp nhiều validator.
- [Spring Framework — Spring MVC Validation Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html): validator toàn cục và validator cục bộ qua `@InitBinder`.

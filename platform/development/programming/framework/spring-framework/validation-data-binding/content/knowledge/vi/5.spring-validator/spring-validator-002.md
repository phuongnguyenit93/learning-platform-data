# `Validator.supports(Class<?>)`: xác định kiểu đối tượng được Spring Validator hỗ trợ

## 1. Mục đích của `supports`

Trong Spring Framework, `org.springframework.validation.Validator` là hợp đồng để kiểm tra các quy tắc dữ liệu trên đối tượng Java. Giao diện này định nghĩa hai phương thức:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

`supports(Class<?> clazz)` trả lời câu hỏi **validator này được thiết kế để kiểm tra đối tượng thuộc kiểu `clazz` hay không?** Nó là bộ lọc khả năng áp dụng theo kiểu (type applicability). Nó **không** kiểm tra giá trị trường, không trả về đối tượng đã sửa, không thực thi Bean Validation constraints và không có nhiệm vụ tạo thông báo lỗi.

`validate(Object target, Errors errors)` mới là nơi kiểm tra giá trị, gọi `errors.reject(...)` hoặc `errors.rejectValue(...)` để ghi nhận các lỗi mà giao diện `Errors`/`BindingResult` cung cấp.

Đây là hai trách nhiệm độc lập:

| Phương thức | Đầu vào | Kết quả | Câu hỏi trả lời |
| --- | --- | --- | --- |
| `supports(Class<?>)` | Đối tượng `Class` | `boolean` | Kiểu này có được validator hỗ trợ không? |
| `validate(Object, Errors)` | Đối tượng dữ liệu và nơi ghi lỗi | `void` | Dữ liệu hiện tại có vi phạm quy tắc không? |

Ví dụ, validator cho `RegistrationForm` có thể trả `true` đối với lớp `RegistrationForm` ngay cả khi một instance cụ thể có email trống. Sai email phải được báo trong `validate`, không quyết định qua `supports`.

## 2. Cách triển khai `supports`

### 2.1. Chỉ nhận đúng một lớp

```java
@Override
public boolean supports(Class<?> clazz) {
    return RegistrationForm.class.equals(clazz);
}
```

Biểu thức trên chỉ trả `true` khi `clazz` đúng bằng `RegistrationForm.class`. Nếu `PremiumRegistrationForm extends RegistrationForm`, lời gọi với `PremiumRegistrationForm.class` trả `false`. Cách này thích hợp khi validator chỉ đúng cho lớp cụ thể và không muốn áp dụng cho các subtype.

### 2.2. Nhận lớp và mọi lớp con

```java
@Override
public boolean supports(Class<?> clazz) {
    return RegistrationForm.class.isAssignableFrom(clazz);
}
```

`Class#isAssignableFrom` trả `true` khi một đối tượng thuộc `clazz` có thể được gán cho biến kiểu `RegistrationForm` (bao gồm chính lớp đó và những subtype phù hợp). Hướng gọi có ý nghĩa:

```java
RegistrationForm.class.isAssignableFrom(PremiumRegistrationForm.class); // true
PremiumRegistrationForm.class.isAssignableFrom(RegistrationForm.class); // false
```

**Lỗi rất thường gặp:** đảo vế thành `clazz.isAssignableFrom(RegistrationForm.class)`. Khi đó có thể nhận cả `Object.class`, trong khi lại từ chối một số subtype của `RegistrationForm` mà validator cần hỗ trợ.

Khi dùng `isAssignableFrom`, logic `validate` cũng phải tương thích với subtype. Nếu validator ép kiểu sang lớp con cụ thể, việc `supports` nhận cả lớp cha sẽ tạo nguy cơ `ClassCastException`.

### 2.3. Validator cho interface hoặc kiểu nền

Có thể áp dụng tương tự với interface:

```java
interface HasContact {
    String contactEmail();
}

// Trong validator chỉ cần các thuộc tính của HasContact:
@Override
public boolean supports(Class<?> clazz) {
    return HasContact.class.isAssignableFrom(clazz);
}
```

Cách này hợp lý khi `validate` chỉ dùng contract của `HasContact`. Chú ý proxy hoặc kiểu runtime có thể khác lớp khai báo; kiểm tra bằng unit test với kiểu thực tế nếu ứng dụng dùng AOP/proxy.

## 3. Ví dụ Java đầy đủ: kiểm tra form đăng ký

Ví dụ Java 17+ sau dùng Spring `Validator` và `BeanPropertyBindingResult`. Đặt vào file `RegistrationValidationDemo.java`:

```java
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class RegistrationValidationDemo {
    public static class RegistrationForm {
        private String email;
        private int age;

        public RegistrationForm(String email, int age) {
            this.email = email;
            this.age = age;
        }

        public String getEmail() { return email; }
        public void setEmail(String email) { this.email = email; }
        public int getAge() { return age; }
        public void setAge(int age) { this.age = age; }
    }

    public static final class PremiumRegistrationForm extends RegistrationForm {
        public PremiumRegistrationForm(String email, int age) {
            super(email, age);
        }
    }

    public static final class RegistrationValidator implements Validator {
        @Override
        public boolean supports(Class<?> clazz) {
            return RegistrationForm.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            RegistrationForm form = (RegistrationForm) target;
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "email", "email.required");
            if (form.getAge() < 18) {
                errors.rejectValue("age", "age.tooYoung");
            }
        }
    }

    public static void main(String[] args) {
        RegistrationValidator validator = new RegistrationValidator();
        System.out.println(validator.supports(RegistrationForm.class));
        System.out.println(validator.supports(PremiumRegistrationForm.class));
        System.out.println(validator.supports(String.class));

        RegistrationForm form = new RegistrationForm("   ", 16);
        BeanPropertyBindingResult errors =
                new BeanPropertyBindingResult(form, "registrationForm");

        if (validator.supports(form.getClass())) {
            validator.validate(form, errors);
        }
        System.out.println(errors.getErrorCount());
        System.out.println(errors.hasFieldErrors("email"));
        System.out.println(errors.hasFieldErrors("age"));
    }
}
```

Khi có `spring-context` hoặc tối thiểu các dependency Spring liên quan (`spring-context`, `spring-beans`, `spring-core` theo dependency graph và phiên bản tương thích) trên classpath, stdout mong đợi là:

```text
true
true
false
2
true
true
```

`supports` nhận `RegistrationForm` và subclass, từ chối `String`. Instance có hai lỗi: email chỉ có khoảng trắng và tuổi dưới 18. `ValidationUtils.rejectIfEmptyOrWhitespace` và `rejectValue` ghi lỗi vào `BeanPropertyBindingResult`. Code này chạy ngoài HTTP; không cần Servlet container hay Spring Boot.

Vì mã sử dụng lớp thuộc Spring, biên dịch bằng JDK trần sẽ thiếu thư viện. Trong dự án Gradle/Maven có dependency Spring phù hợp, biên dịch/chạy qua classpath của dự án. Nếu có một classpath đã phân giải đầy đủ trong biến môi trường `SPRING_CP`, có thể dùng:

```bash
javac -cp "$SPRING_CP" RegistrationValidationDemo.java
java -cp ".:$SPRING_CP" RegistrationValidationDemo
```

Lệnh trên dùng cú pháp classpath của Linux/macOS. Trên Windows, dấu ngăn cách classpath là `;`, ví dụ `java -cp ".;%SPRING_CP%" RegistrationValidationDemo` trong `cmd.exe`. Biến `SPRING_CP` phải trỏ đến tất cả JAR cần thiết; code không tự tải dependencies.

## 4. Vai trò trong quá trình Spring Web MVC data binding

Trong ứng dụng MVC, `WebDataBinder` xử lý binding và hỗ trợ đăng ký validators. Người phát triển thường dùng `@InitBinder` để áp dụng validator cho model/form nhất định. Ví dụ:

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.RestController;

@RestController
class RegistrationController {
    private final RegistrationValidationDemo.RegistrationValidator validator =
            new RegistrationValidationDemo.RegistrationValidator();

    @InitBinder("registrationForm")
    void registerValidator(WebDataBinder binder) {
        binder.addValidators(validator);
    }

    @PostMapping("/register")
    String register(
            @ModelAttribute("registrationForm")
            RegistrationValidationDemo.RegistrationForm form,
            BindingResult bindingResult) {
        if (bindingResult.hasErrors()) {
            return "Invalid registration";
        }
        return "Accepted";
    }
}
```

Đây là **đoạn minh họa controller** đặt trong một ứng dụng Spring MVC có `RegistrationValidationDemo` trên classpath. Để kích hoạt kiểm tra `Validator` cho model attribute, sử dụng `@Validated` hoặc `@Valid` trên tham số theo cấu hình MVC, hoặc gọi `binder.validate()` ở luồng thích hợp. **Chỉ thêm validator bằng `binder.addValidators(...)` không bảo đảm `validate` tự chạy cho mọi request**.

Với một thiết lập thông thường, controller có thể viết:

```java
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.ModelAttribute;

// Phần chữ ký phương thức trong controller MVC:
String register(
        @Validated @ModelAttribute("registrationForm")
        RegistrationValidationDemo.RegistrationForm form,
        BindingResult bindingResult) {
    return bindingResult.hasErrors() ? "Invalid registration" : "Accepted";
}
```

Khi Spring áp dụng validator đã đăng ký, `supports` giúp kiểm tra validator có phù hợp với target type. Một validator không hỗ trợ kiểu đối tượng có thể dẫn đến lỗi cấu hình tại bước đăng ký/áp dụng hoặc không được chọn tùy API và đường thực thi. Không nên dựa vào việc framework âm thầm bỏ qua mọi validator sai kiểu.

Quan trọng: `BindingResult` phải đứng ngay sau tham số được bind/validated tương ứng; nếu không, lỗi có thể được xử lý theo cơ chế exception của MVC thay vì trả về trong biến mà controller dự định đọc.

## 5. Spring lựa chọn validator và kiểm tra `supports` ở đâu?

Có hai tình huống thường gặp:

1. **Tự gọi `Validator`**: code ứng dụng cần chủ động gọi `supports` nếu muốn lọc theo kiểu trước `validate`, bởi interface không tự kích hoạt quá trình chọn validator.
2. **Đăng ký qua binder**: Spring kiểm tra tính tương thích của validator với target trong các thao tác đăng ký/xử lý cụ thể. Nếu không phù hợp, API có thể từ chối (ví dụ `addValidators` trên binder có target không được hỗ trợ); cần chọn validator phù hợp hoặc phạm vi `@InitBinder` thích hợp.

Ví dụ kiểm tra an toàn khi tự gọi:

```java
public static void validateIfSupported(
        org.springframework.validation.Validator validator,
        Object target,
        org.springframework.validation.Errors errors) {
    if (!validator.supports(target.getClass())) {
        throw new IllegalArgumentException(
                "Unsupported target type: " + target.getClass().getName());
    }
    validator.validate(target, errors);
}
```

Đây là helper minh họa, không phải quy tắc Spring bắt buộc dùng cho mọi API. Nếu `target` có thể `null`, cần xử lý rõ trước khi gọi `getClass()`.

### 5.1. `setValidator`, `addValidators` và `replaceValidators`

`DataBinder`/`WebDataBinder` cung cấp các API quản lý validator. Tùy phiên bản Spring, `setValidator` đặt validator chính, `addValidators` bổ sung validators và `replaceValidators` thay thế danh sách. Các API có thể kiểm tra `supports` đối với kiểu target đang được bind. Hãy chú ý thứ tự đăng ký, phạm vi binder và cơ chế kích hoạt validate; điều đó quyết định những validator nào được chạy thực tế.

Đăng ký validator không có nghĩa nó xử lý được mọi model. Ví dụ `RegistrationValidator` không được dùng cho `InvoiceForm` nếu `supports(InvoiceForm.class)` trả `false`.

### 5.2. `SmartValidator` và validation hints

`SmartValidator` mở rộng hợp đồng Spring `Validator` để hỗ trợ `validate(Object, Errors, Object... validationHints)`. Các hints có thể được cung cấp bởi `@Validated` trong những kịch bản phù hợp, chẳng hạn validation groups. `supports(Class<?>)` vẫn trả lời về khả năng hỗ trợ kiểu; nó không phải nơi xử lý từng validation group. Bean Validation adapter của Spring có thể triển khai `SmartValidator` để kết nối Jakarta Bean Validation với hạ tầng Spring.

## 6. Thiết kế một `supports` đúng và bền vững

### 6.1. Kiểu được hỗ trợ phải tương ứng logic `validate`

```java
@Override
public boolean supports(Class<?> clazz) {
    return RegistrationForm.class.isAssignableFrom(clazz);
}

@Override
public void validate(Object target, Errors errors) {
    RegistrationForm form = (RegistrationForm) target;
    // Kiểm tra các trường có trong RegistrationForm.
}
```

Nếu `supports` nhận subclass thì `validate` chỉ nên dựa vào thuộc tính chung của lớp cha, trừ khi có logic tách theo subtype rõ ràng.

### 6.2. Tránh cast và lỗi kiểu

Không viết kiểu:

```java
@Override
public boolean supports(Class<?> clazz) {
    return true;
}

@Override
public void validate(Object target, Errors errors) {
    RegistrationForm form = (RegistrationForm) target;
}
```

`supports` luôn `true` nhưng `validate` cast vô điều kiện sẽ lỗi với target khác kiểu. Điều này rất dễ xảy ra nếu validator được gắn cho binder có phạm vi rộng.

### 6.3. Không dùng `supports` để kiểm tra nội dung dữ liệu

Không thể kiểm tra `email` rỗng hay `age` quá nhỏ bằng `Class<?>`: các instance cùng lớp có giá trị khác nhau. Nội dung của trường thuộc về `validate` và lỗi nên được ghi với `Errors` để caller có thể hiển thị thông báo.

### 6.4. Cân nhắc proxy, inheritance và khả năng tái sử dụng

Khi áp dụng lên subtype, hãy dùng `isAssignableFrom` nếu đúng với contract dữ liệu. Với proxy, kiểu được framework truyền vào có thể là kiểu runtime; không nên viết so sánh lớp quá hẹp nếu ứng dụng thực sự dùng subclass/proxy tương thích. Ngược lại, nếu validation chỉ áp dụng cho đúng một loại form có semantics riêng, `equals` có thể phù hợp hơn.

### 6.5. Lỗi binding và lỗi validation là hai giai đoạn

Form `age=abc` không thể chuyển thành `int`: lỗi có thể xảy ra ở data binding trước khi validator xem tuổi có đủ 18 hay không. `supports` không chữa lỗi chuyển đổi chuỗi. Cần phân biệt lỗi `typeMismatch` với lỗi nghiệp vụ như `age.tooYoung`, và xử lý cả hai theo mô hình response nhất quán.

## 7. Kiểm thử `supports` và `validate`

Một bộ kiểm thử tối thiểu nên xác nhận:

| Trường hợp | Kỳ vọng |
| --- | --- |
| `supports(RegistrationForm.class)` | `true` |
| `supports(PremiumRegistrationForm.class)` | `true` khi dùng `isAssignableFrom` |
| `supports(String.class)` | `false` |
| Form email hợp lệ, age >= 18 | `Errors` không có lỗi từ các quy tắc này |
| Form email rỗng hoặc whitespace | Lỗi field `email` |
| Form age < 18 | Lỗi field `age` |
| Target khác kiểu | Không gọi `validate` khi `supports` là `false` |

Ví dụ JUnit 5 (trong project có Spring và JUnit dependency phù hợp):

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.validation.BeanPropertyBindingResult;

class RegistrationValidatorTest {
    private final RegistrationValidationDemo.RegistrationValidator validator =
            new RegistrationValidationDemo.RegistrationValidator();

    @Test
    void supportsParentAndSubtypeButNotString() {
        assertTrue(validator.supports(
                RegistrationValidationDemo.RegistrationForm.class));
        assertTrue(validator.supports(
                RegistrationValidationDemo.PremiumRegistrationForm.class));
        assertFalse(validator.supports(String.class));
    }

    @Test
    void rejectsEmptyEmailAndTooYoungAge() {
        var form = new RegistrationValidationDemo.RegistrationForm(" ", 16);
        var errors = new BeanPropertyBindingResult(form, "registrationForm");
        validator.validate(form, errors);
        assertTrue(errors.hasFieldErrors("email"));
        assertTrue(errors.hasFieldErrors("age"));
    }
}
```

`supports` nên nhất quán và nhanh vì nó có thể được gọi khi thiết lập hoặc chạy validation. Không cần tải database hay gọi HTTP trong phương thức chỉ nhằm xác định kiểu hỗ trợ.

## 8. Ghi nhớ

- `supports` kiểm tra **kiểu**, còn `validate` kiểm tra **giá trị**.
- Dùng `MyForm.class.equals(clazz)` cho đúng lớp; dùng `MyForm.class.isAssignableFrom(clazz)` khi hỗ trợ cả subtype.
- Hướng của `isAssignableFrom` rất quan trọng: đặt kiểu mà validator hỗ trợ ở **bên trái**.
- Giữ phạm vi validator gắn với đúng model hoặc binder; đừng để một validator hẹp được đăng ký cho mọi kiểu.
- Với Spring MVC, đăng ký validator và kích hoạt validation là hai bước cần phân biệt.
- Luôn kiểm thử `supports` trên lớp đích, subclass và lớp không liên quan, rồi kiểm tra lỗi do `validate` tạo ra.

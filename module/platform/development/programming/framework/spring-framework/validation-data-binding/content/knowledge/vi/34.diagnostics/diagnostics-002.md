# Chẩn đoán `supports()` trả về `false` và validator không phù hợp kiểu đích trong Spring

## 1. Vấn đề: lỗi kiểu đích khác lỗi dữ liệu

Một `org.springframework.validation.Validator` của Spring trả lời hai câu hỏi khác nhau:

~~~java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

- `supports(clazz)` cho biết validator có **khả năng xử lý class** được truyền vào không.
- `validate(target, errors)` kiểm tra **giá trị của object đã đúng kiểu** và ghi field/global errors.
- `supports() == false` không có nghĩa một giá trị business không hợp lệ. Nó có nghĩa **validator không phù hợp với target type**.
- `validate(...)` trả `void`, không trả boolean như `supports`.

Ví dụ `UserFormValidator` chuyên kiểm tra `UserForm`. Khi form hợp lệ hay sai tuổi, `supports(UserForm.class)` đều phải là `true`. Nếu đăng ký `UserFormValidator` lên binder đang giữ `OrderForm`, `supports(OrderForm.class)` là `false`: đây là **lỗi cấu hình hoặc điều phối sai validator**, không phải một `FieldError` mà người dùng có thể sửa.

Spring 6.1/6.2 có những biểu hiện điển hình:

~~~text
DataBinder.setValidator(...) + target không phù hợp
    -> IllegalStateException

DataBinder.addValidators(...) + target không phù hợp
    -> IllegalStateException

ValidationUtils.invokeValidator(...) + target không phù hợp
    -> IllegalArgumentException

Gọi validator.validate(...) trực tiếp với target sai type
    -> Có thể ClassCastException hoặc xử lý sai
~~~

Vì thế, đừng viết một exception handler trả HTTP 400 cho mọi lỗi có chữ Validator. Với mismatch do chính server gắn sai validator, đó thường là **lỗi server-side**, cần sửa cấu hình/logic và theo dõi 5xx an toàn.

## 2. Phân biệt tương thích type với kết quả validation

| Tình huống | `supports` | `validate`/Errors | Ý nghĩa |
| --- | --- | --- | --- |
| `UserForm` với name tốt, age 22 | true | Không có lỗi | Đúng type, dữ liệu hợp lệ |
| `UserForm` với name rỗng | true | Có field error ở name | Đúng type, dữ liệu sai |
| `UserForm` với age 16 | true | Có field error ở age | Đúng type, business rule sai |
| `OrderForm` đưa cho UserFormValidator | false | Không nên gọi `validate` | Sai type, cần sửa cách đăng ký |
| Subclass `PremiumUserForm` | Tùy hợp đồng `supports` | Nếu hỗ trợ thì validate theo UserForm | Cần test inheritance |
| Jakarta Bean Validation `@NotBlank` | Không phải phương thức cùng tên trên Jakarta Validator | Tạo ConstraintViolation qua provider | Cơ chế khác, được Spring tích hợp qua adapter |

Một implementation Spring Validator tiêu biểu:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return UserForm.class.isAssignableFrom(clazz);
}

@Override
public void validate(Object target, Errors errors) {
    UserForm form = (UserForm) target;

    if (form.getAge() != null && form.getAge() < 18) {
        errors.rejectValue("age", "user.age.minimum");
    }
}
~~~

`supports` chỉ xét class. Nó **không** đọc tuổi, không truy vấn database và không ném exception để báo một giá trị xấu. `validate` chỉ chạy khi target phù hợp; nó ghi `Errors` thông qua `rejectValue`/`reject`.

### Vì sao `Class#isAssignableFrom` dễ bị đảo ngược?

Khi mong muốn hỗ trợ `UserForm` và subclass, công thức đúng là:

~~~java
return UserForm.class.isAssignableFrom(clazz);
~~~

Hãy đọc: instance thuộc `clazz` có thể gán vào biến `UserForm`. Ví dụ:

| `clazz` | Kết quả đúng |
| --- | --- |
| `UserForm.class` | true |
| `PremiumUserForm.class` (extends UserForm) | true |
| `OrderForm.class` | false |
| `Object.class` | false |

Công thức dễ viết sai:

~~~java
// SAI nếu muốn hỗ trợ subclass UserForm:
return clazz.isAssignableFrom(UserForm.class);
~~~

Với cách đảo chiều, `supports(Object.class)` có thể trả `true`, nhưng `supports(PremiumUserForm.class)` trả `false`. Nếu chỉ unit test với đúng `UserForm.class`, lỗi này không bị bắt.

So sánh chính xác:

~~~java
return clazz == UserForm.class;
~~~

không nhất thiết sai nếu thiết kế chỉ cho phép **đúng class UserForm**, không cho subclass/proxy. Nhưng khi yêu cầu chấp nhận subtype thì phải chọn `isAssignableFrom` đúng chiều. Không tự biến mọi validator thành `supports(clazz) { return true; }` để né lỗi, vì sau đó việc cast và các property paths vẫn có thể không hợp lệ.

### Class và object name không giống nhau

~~~java
new DataBinder(new UserForm(), "createUser");
new DataBinder(new UserForm(), "editUser");
~~~

Hai binder có object name khác nhau nhưng **cùng Java class**, nên `supports(UserForm.class)` có cùng kết quả.

~~~java
new DataBinder(new UserForm(), "form");
new DataBinder(new OrderForm(), "form");
~~~

Hai binder này có object name giống nhau nhưng **khác Java class**. `supports` kiểm tra Java type, không tự dựa vào chuỗi object name.

## 3. Spring phát hiện mismatch vào thời điểm nào?

### 3.1. Đăng ký validator trên `DataBinder` đã có target

~~~java
OrderForm order = new OrderForm();
DataBinder binder = new DataBinder(order, "orderForm");

binder.setValidator(new UserFormValidator());
~~~

Trong Spring 6.1/6.2, khi target đã tồn tại, `DataBinder` kiểm tra `validator.supports(target.getClass())` lúc đăng ký. Nếu không khớp, `setValidator(...)` ném **`IllegalStateException`**. `addValidators(...)` và `replaceValidators(...)` cũng kiểm tra khả năng hỗ trợ với target non-null.

JUnit test:

~~~java
var binder = new DataBinder(new OrderForm(), "orderForm");

assertThrows(IllegalStateException.class,
        () -> binder.addValidators(new UserFormValidator()));
~~~

**Không xem đây là conversion error** hay validation error. Việc đăng ký chưa thành công; `BindingResult` không nhất thiết có `FieldError`.

### 3.2. Gọi `ValidationUtils.invokeValidator`

~~~java
OrderForm order = new OrderForm();
var errors = new BeanPropertyBindingResult(
        order, "orderForm");

ValidationUtils.invokeValidator(
        new UserFormValidator(), order, errors);
~~~

`ValidationUtils.invokeValidator(...)` trước tiên kiểm tra `supports(order.getClass())`. Không phù hợp sẽ ném **`IllegalArgumentException`**. Unit test:

~~~java
assertThrows(IllegalArgumentException.class,
        () -> ValidationUtils.invokeValidator(
                new UserFormValidator(), order, errors));
~~~

Đây là hành vi được Spring Javadoc ghi rõ; tránh suy đoán exception chỉ từ chữ `Validator` trong tên class.

### 3.3. Gọi `validate` trực tiếp rồi cast sai

~~~java
// Không nên làm:
new UserFormValidator().validate(
        new OrderForm(),
        new BeanPropertyBindingResult(
                new OrderForm(), "orderForm"));
~~~

Nếu implementation cast `(UserForm) target` thì một `ClassCastException` có thể xuất hiện. Lời gọi trực tiếp **bỏ qua guard của `ValidationUtils`**. Không giải quyết bằng cách nuốt ClassCastException: đó là mismatch type trong code, không phải một giá trị đầu vào sai quy tắc.

### 3.4. Target của binder có thể chưa được tạo

Trong một số đường constructor binding, `DataBinder` có thể tồn tại với target null và target type được cấu hình trước khi tạo object. Khi target null, không thể dùng `target.getClass()` để kiểm tra supports ngay lúc đăng ký. Do vậy một cấu hình sai có thể chỉ bộc lộ **muộn hơn** trong argument resolution/validation.

Không kết luận rằng validator phù hợp chỉ vì `setValidator` chưa ném exception lúc target null. Cần kiểm thử trên **endpoint thật** và đúng đường tạo object.

### 3.5. Không phụ thuộc nội dung `toString()` trong exception

Exception message của binder có thể chứa target hoặc class name. Không khẳng định một thông điệp cụ thể bất biến theo Spring version. Tests nên ưu tiên **exception type** và kết quả dữ liệu. Logs/HTTP response không nên in raw `target.toString()`, toàn bộ `BindingResult` hay rejected values (có thể chứa mật khẩu, email, token).

## 4. Khi nào validator chạy và tại sao không có field errors?

`DataBinder#bind(...)` và `DataBinder#validate()` là hai bước riêng:

~~~java
DataBinder binder =
        new DataBinder(new UserForm(), "userForm");

binder.setValidator(new UserFormValidator());

binder.bind(new MutablePropertyValues(Map.of(
        "displayName", "",
        "age", "16"
)));

// Chỉ binding đã chạy; custom validation chưa chạy.
boolean before = binder.getBindingResult().hasErrors();

binder.validate();

// Sau đó custom validation mới ghi field errors.
boolean after = binder.getBindingResult().hasErrors();
~~~

Với implementation ở phần 8, `before == false` và `after == true`. **Đây là kết quả của ví dụ khi chuỗi tuổi chuyển thành Integer thành công**. Nếu bind dữ liệu có `age=abc`, Spring có thể tạo `typeMismatch` ngay ở bước bind nên `before` có thể true — một cơ chế khác.

Trong Spring MVC, `@Valid`/`@Validated` trên argument có thể kích hoạt validation sau binding; `BindingResult` đặt ngay sau argument cho phép controller nhận errors. Nếu thiếu trigger `@Valid`, dù đã đăng ký custom Spring validator, đừng giả định nó sẽ tự chạy.

### Đọc `getValidator()` hay `getValidators()`?

`getValidator()` trả primary validator nếu có. `getValidators()` cho danh sách đầy đủ đã đăng ký. Spring 6.1+ có `getValidatorsToApply()`, phản ánh danh sách sau exclusion predicate khi áp dụng.

Nếu có nhiều validators, kiểm tra đầy đủ:

~~~java
List<Validator> all = binder.getValidators();
List<Validator> active = binder.getValidatorsToApply();
~~~

Đây là snippet có imports tương ứng, không phải toàn bộ class độc lập. `setExcludedValidators(Predicate<Validator>)` là filter lúc áp dụng validators, **không phải phương pháp sửa một validator sai target đã thất bại khi đăng ký**.

## 5. `setValidator`, `addValidators` và `replaceValidators`

| API | Tác dụng | Lỗi thường gặp |
| --- | --- | --- |
| `setValidator(v)` | Thay danh sách validator hiện có bằng validator v; `null` có thể clear. | Mất global Jakarta Bean Validation adapter do bị thay thế. |
| `addValidators(v)` | Bổ sung validator vào danh sách hiện có. | Gắn validator cục bộ sai type khi dùng trên mọi form. |
| `replaceValidators(v1, v2)` | Thay danh sách bằng những validators đã liệt kê. | Một trong các validators không hỗ trợ target. |
| `getValidators()` | Xem toàn bộ danh sách đã đăng ký. | Không dùng nên bỏ sót validator thứ hai. |
| `getValidatorsToApply()` | Danh sách áp dụng sau khi loại theo predicate, Spring 6.1+. | Tưởng nó làm `supports` của validator sai thành true. |

Nếu ứng dụng có `spring-boot-starter-validation`, Spring MVC thường sử dụng `LocalValidatorFactoryBean` để chạy Jakarta Bean Validation. Khi thêm custom Spring validator trong `@InitBinder`, cách thường phù hợp là:

~~~java
binder.addValidators(userFormValidator);
~~~

thay vì `setValidator(userFormValidator)` nếu muốn **giữ cả Bean Validation global lẫn custom rules**. Tuy nhiên bản thân `addValidators` cũng sẽ không chấp nhận validator sai type với target đã tồn tại.

### Vấn đề scope của `@InitBinder`

Sai khi controller có nhiều target classes:

~~~java
@InitBinder
void initEveryBinder(WebDataBinder binder) {
    binder.addValidators(userFormValidator);
}
~~~

Không nêu object name thì callback có thể áp dụng cho nhiều model attributes. Khi một handler dùng `OrderForm`, `UserFormValidator` không phù hợp. Cách sửa:

~~~java
@InitBinder("userForm")
void initUser(WebDataBinder binder) {
    binder.addValidators(userFormValidator);
}

@InitBinder("orderForm")
void initOrder(WebDataBinder binder) {
    binder.addValidators(orderFormValidator);
}
~~~

**Hai cơ chế khác nhau cùng phải đúng**:

- `@InitBinder("userForm")`: giới hạn cấu hình theo **object name**.
- `supports(UserForm.class)`: kiểm tra **Java type**.

Đừng chỉ đổi tên `@InitBinder` mà không kiểm tra actual target type. Cũng đừng bắt tất cả exceptions trong `@ControllerAdvice` rồi trả HTTP 400, vì mismatch do server thiết lập validator sai không phải lỗi form của người dùng.

## 6. Một quy trình chẩn đoán nhanh, có thể lặp lại

Khi gặp log lỗi `Invalid target for Validator` hoặc `Validator ... does not support ...`, lần lượt kiểm tra:

1. **Thời điểm:** đang gọi `setValidator`/`addValidators` hay `ValidationUtils.invokeValidator` hoặc đã vào `validate`?
2. **Target runtime:** `binder.getTarget()` là null hay đã có object? Nếu có, `getTarget().getClass()` là class nào?
3. **Object name:** `binder.getObjectName()` có đúng tên `@ModelAttribute("...")` không?
4. **Supports:** `customValidator.supports(runtimeClass)` có đúng như dự kiến không? Unit test exact, subtype, unrelated, `Object.class`.
5. **Các validator đã đăng ký:** có Bean Validation global, custom validator, hoặc validator bị thay thế bởi `setValidator` không?
6. **Controller binding lifecycle:** `@InitBinder` có áp dụng quá rộng cho cả form khác không? Có `@ControllerAdvice` toàn cục không?
7. **Phần thân validate:** có cast không đúng hoặc `rejectValue` cho property không thuộc target không?
8. **Validation trigger:** MVC handler có `@Valid`/`@Validated`, hay code đang dùng `DataBinder.bind` nhưng chưa gọi `validate`?
9. **Pipeline:** request là `@ModelAttribute`, `@RequestBody` JSON, WebFlux hay service method? Không dùng một chẩn đoán cho mọi stack.
10. **Regression tests:** có test minh họa form sai type và form đúng type sau khi sửa không?

Metadata để debug:

~~~java
Object target = binder.getTarget();

Class<?> runtimeType =
        target != null ? target.getClass() : null;

boolean supported = runtimeType != null
        && userFormValidator.supports(runtimeType);
~~~

Không log toàn bộ target/`BindingResult` vì có thể tiết lộ rejected values. Có thể log **class name, binder object name, error category** trong hệ thống log đã kiểm soát.

## 7. Spring Validator khác Jakarta Bean Validation

| Spring interface | Jakarta interface |
| --- | --- |
| `org.springframework.validation.Validator` | `jakarta.validation.Validator` |
| Có `supports(Class<?>)` | Không có cùng API `supports(Class<?>)` |
| `validate(Object, Errors)` ghi lỗi vào Spring `Errors` | `validate(T, Class<?>... groups)` trả `Set<ConstraintViolation<T>>` |
| Dùng trong `DataBinder#setValidator/addValidators` | Được tích hợp qua `LocalValidatorFactoryBean` hoặc adapter Spring |
| Hữu ích cho rule object/domain cục bộ | Dựa trên `@NotBlank`, `@Min`, `@Email` và custom constraints |

`org.springframework.validation.SmartValidator` còn thêm overload với validation hints:

~~~java
void validate(
        Object target,
        Errors errors,
        Object... validationHints);
~~~

Các hints có thể đại diện validation groups, tùy implementation. **Validation hints không sửa một `supports(false)`**. Nếu validator không hỗ trợ runtime target class, phải sửa registration/type ngay cả khi đã truyền đúng group.

`@Valid` chỉ kích hoạt kiểm tra theo pipeline, không tự tạo rule từ không khí. Nếu DTO không có Jakarta constraints và cũng không gắn Spring Validator phù hợp, `@Valid` có thể không tạo errors.

## 8. Ví dụ chạy được: Java 17+, Spring Boot 3.2+, JUnit 5

Dự án gồm **hai model khác nhau**, hai Spring validators tương ứng, một controller và hai lớp test. Chọn Spring Boot 3.2+ (Framework 6.1+) với patch release phù hợp security policy của tổ chức. Dùng Java 17+.

Trong Maven project đã cấu hình Spring Boot parent/BOM, thêm dependencies:

~~~xml
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
~~~

Package: `com.example.validatorchecks`. Files chính ở `src/main/java/com/example/validatorchecks/`, tests ở `src/test/java/com/example/validatorchecks/`.

### 8.1. `ValidatorChecksApplication.java`

~~~java
package com.example.validatorchecks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidatorChecksApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ValidatorChecksApplication.class, args);
    }
}
~~~

### 8.2. `UserForm.java`

~~~java
package com.example.validatorchecks;

public class UserForm {
    private String displayName;
    private Integer age;

    public UserForm() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String value) {
        this.displayName = value;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer value) {
        this.age = value;
    }
}
~~~

### 8.3. `OrderForm.java`

~~~java
package com.example.validatorchecks;

public class OrderForm {
    private String code;

    public OrderForm() {
    }

    public String getCode() {
        return code;
    }

    public void setCode(String value) {
        this.code = value;
    }
}
~~~

`OrderForm` không kế thừa `UserForm`; đây là test case cho `supports == false`.

### 8.4. `UserFormValidator.java`

~~~java
package com.example.validatorchecks;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

@Component
public final class UserFormValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return UserForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        UserForm user = (UserForm) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "displayName", "user.name.required");

        if (user.getAge() == null) {
            errors.rejectValue("age", "user.age.required");
        }
        else if (user.getAge() < 18) {
            errors.rejectValue("age", "user.age.minimum");
        }
    }
}
~~~

`supports` trả true với `UserForm` và subclass, false với `OrderForm`. `validate` cast đúng vào `UserForm`, rồi tạo `FieldError` nếu name/age sai. Không log giá trị, không có state theo request và không query database.

### 8.5. `OrderFormValidator.java`

~~~java
package com.example.validatorchecks;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

@Component
public final class OrderFormValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return OrderForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "code", "order.code.required");
    }
}
~~~

### 8.6. `DiagnosticsController.java`

~~~java
package com.example.validatorchecks;

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

@RestController
@RequestMapping("/diagnostics")
public class DiagnosticsController {

    private final UserFormValidator users;
    private final OrderFormValidator orders;

    public DiagnosticsController(
            UserFormValidator users,
            OrderFormValidator orders) {
        this.users = users;
        this.orders = orders;
    }

    @InitBinder("userForm")
    void configureUser(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "age");
        // Giữ global Bean Validation validator nếu có.
        binder.addValidators(users);
    }

    @InitBinder("orderForm")
    void configureOrder(WebDataBinder binder) {
        binder.setAllowedFields("code");
        binder.addValidators(orders);
    }

    @PostMapping(path = "/users",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    ResponseEntity<String> user(
            @Valid @ModelAttribute("userForm") UserForm form,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body("INVALID_USER");
        }

        return ResponseEntity.ok(
                "USER:" + form.getDisplayName()
                + ":" + form.getAge());
    }

    @PostMapping(path = "/orders",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    ResponseEntity<String> order(
            @Valid @ModelAttribute("orderForm") OrderForm form,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body("INVALID_ORDER");
        }

        return ResponseEntity.ok(
                "ORDER:" + form.getCode());
    }
}
~~~

Tác dụng thiết kế: `@InitBinder("userForm")` chỉ thêm `UserFormValidator` cho attribute đúng tên; `@InitBinder("orderForm")` làm tương tự cho `OrderFormValidator`. `@Valid` trigger validation; `BindingResult` ngay sau argument nhận errors. `setAllowedFields` giảm rủi ro mass assignment, nhưng **không thay thế `supports` hay authorization**.

## 9. Unit tests: `supports`, exception đúng chỗ và kết quả validate

Tạo file `src/test/java/com/example/validatorchecks/ValidatorCompatibilityTest.java`:

~~~java
package com.example.validatorchecks;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class ValidatorCompatibilityTest {

    private final UserFormValidator users =
            new UserFormValidator();
    private final OrderFormValidator orders =
            new OrderFormValidator();

    static class PremiumUserForm extends UserForm {
    }

    @Test
    void supportsExactType() {
        assertTrue(users.supports(UserForm.class));
    }

    @Test
    void supportsSubclass() {
        assertTrue(users.supports(PremiumUserForm.class));
    }

    @Test
    void rejectsUnrelatedAndSuperclassTypes() {
        assertFalse(users.supports(OrderForm.class));
        assertFalse(users.supports(Object.class));
        assertFalse(orders.supports(UserForm.class));
    }

    @Test
    void wrongAssignableDirectionWouldRejectSubclass() {
        assertFalse(PremiumUserForm.class
                .isAssignableFrom(UserForm.class));
    }

    @Test
    void mismatchedSetValidatorThrows() {
        DataBinder binder = new DataBinder(
                new OrderForm(), "orderForm");
        assertThrows(IllegalStateException.class,
                () -> binder.setValidator(users));
    }

    @Test
    void mismatchedAddValidatorsThrows() {
        DataBinder binder = new DataBinder(
                new OrderForm(), "orderForm");
        assertThrows(IllegalStateException.class,
                () -> binder.addValidators(users));
    }

    @Test
    void mismatchedReplaceValidatorsThrows() {
        DataBinder binder = new DataBinder(
                new OrderForm(), "orderForm");
        assertThrows(IllegalStateException.class,
                () -> binder.replaceValidators(users));
    }

    @Test
    void validationUtilsMismatchThrowsDifferentException() {
        OrderForm order = new OrderForm();
        var errors = new BeanPropertyBindingResult(
                order, "orderForm");
        assertThrows(IllegalArgumentException.class,
                () -> ValidationUtils.invokeValidator(
                        users, order, errors));
    }

    @Test
    void validationUtilsCorrectTargetCreatesFieldErrors() {
        UserForm user = new UserForm();
        user.setDisplayName("");
        user.setAge(16);
        var errors = new BeanPropertyBindingResult(
                user, "userForm");

        ValidationUtils.invokeValidator(users, user, errors);

        assertTrue(errors.hasFieldErrors("displayName"));
        assertTrue(errors.hasFieldErrors("age"));
    }

    @Test
    void bindAloneDoesNotRunCustomValidation() {
        UserForm user = new UserForm();
        DataBinder binder = new DataBinder(user, "userForm");
        binder.setValidator(users);

        binder.bind(new MutablePropertyValues(Map.of(
                "displayName", "",
                "age", "16")));

        assertFalse(binder.getBindingResult().hasErrors());

        binder.validate();

        assertTrue(binder.getBindingResult()
                .hasFieldErrors("displayName"));
        assertTrue(binder.getBindingResult()
                .hasFieldErrors("age"));
    }

    @Test
    void validUserHasNoErrors() {
        UserForm user = new UserForm();
        DataBinder binder = new DataBinder(user, "userForm");
        binder.setValidator(users);
        binder.bind(new MutablePropertyValues(Map.of(
                "displayName", "Lan",
                "age", "22")));
        binder.validate();

        assertFalse(binder.getBindingResult().hasErrors());
        assertEquals("Lan", user.getDisplayName());
        assertEquals(22, user.getAge());
    }

    @Test
    void orderValidatorRunsOnOrder() {
        OrderForm order = new OrderForm();
        DataBinder binder = new DataBinder(order, "orderForm");
        binder.setValidator(orders);
        binder.bind(new MutablePropertyValues(
                Map.of("code", "")));
        binder.validate();

        assertTrue(binder.getBindingResult()
                .hasFieldErrors("code"));
    }

    @Test
    void setValidatorReplacesPreviousValidator() {
        UserForm user = new UserForm();
        DataBinder binder = new DataBinder(user, "userForm");

        Validator noop = new Validator() {
            @Override
            public boolean supports(Class<?> c) {
                return true;
            }
            @Override
            public void validate(Object target, Errors errors) {
            }
        };

        binder.setValidator(noop);
        binder.setValidator(users);

        assertEquals(1, binder.getValidators().size());
        assertSame(users, binder.getValidator());
    }

    @Test
    void addValidatorsKeepsEarlierCompatibleValidator() {
        UserForm user = new UserForm();
        DataBinder binder = new DataBinder(user, "userForm");

        Validator noop = new Validator() {
            @Override
            public boolean supports(Class<?> c) {
                return UserForm.class.isAssignableFrom(c);
            }
            @Override
            public void validate(Object target, Errors errors) {
            }
        };

        binder.setValidator(noop);
        binder.addValidators(users);

        assertEquals(2, binder.getValidators().size());
        user.setAge(16);
        binder.validate();
        assertTrue(binder.getBindingResult()
                .hasFieldErrors("age"));
    }

    @Test
    void setValidatorNullClears() {
        DataBinder binder = new DataBinder(
                new UserForm(), "userForm");
        binder.setValidator(users);
        binder.setValidator(null);
        assertEquals(0, binder.getValidators().size());
    }

    @Test
    void excludedValidatorDoesNotRun() {
        UserForm user = new UserForm();
        user.setAge(16);
        DataBinder binder = new DataBinder(user, "userForm");
        binder.addValidators(users);
        binder.setExcludedValidators(
                v -> v instanceof UserFormValidator);

        assertEquals(1, binder.getValidators().size());
        assertEquals(0, binder.getValidatorsToApply().size());

        binder.validate();
        assertFalse(binder.getBindingResult().hasErrors());
    }
}
~~~

**16 unit tests** kiểm tra: exact type, subtype, unrelated/superclass; ba cách đăng ký sai type đều ném `IllegalStateException`; `ValidationUtils.invokeValidator` sai type ném `IllegalArgumentException`; bind khác validate; validation tạo field errors; thứ tự/ý nghĩa của `setValidator`, `addValidators`, `setExcludedValidators`.

Lưu ý: các test dựa trên `DataBinder` **có target non-null**, Spring Framework 6.1/6.2. Khi target chưa được tạo hoặc Spring version khác, thời điểm lỗi có thể thay đổi. Không hardcode exception message có thể chứa target state.

## 10. MockMvc integration tests: chứng minh @InitBinder được áp dụng đúng

Tạo `src/test/java/com/example/validatorchecks/DiagnosticsControllerTest.java`:

~~~java
package com.example.validatorchecks;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class DiagnosticsControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validUser() throws Exception {
        mvc.perform(post("/diagnostics/users")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("age", "22"))
                .andExpect(status().isOk())
                .andExpect(content().string("USER:Lan:22"));
    }

    @Test
    void blankName() throws Exception {
        mvc.perform(post("/diagnostics/users")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "")
                    .param("age", "22"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_USER"));
    }

    @Test
    void underage() throws Exception {
        mvc.perform(post("/diagnostics/users")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("age", "16"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_USER"));
    }

    @Test
    void missingAge() throws Exception {
        mvc.perform(post("/diagnostics/users")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_USER"));
    }

    @Test
    void conversionMismatchIsNotSupportsMismatch()
            throws Exception {
        mvc.perform(post("/diagnostics/users")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("age", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_USER"));
    }

    @Test
    void extraUserPropertyIsSuppressed() throws Exception {
        mvc.perform(post("/diagnostics/users")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("displayName", "Lan")
                    .param("age", "22")
                    .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_USER"));
    }

    @Test
    void validOrderDoesNotUseUserValidator()
            throws Exception {
        mvc.perform(post("/diagnostics/orders")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("code", "O-001"))
                .andExpect(status().isOk())
                .andExpect(content().string("ORDER:O-001"));
    }

    @Test
    void blankOrderCodeUsesOrderValidator()
            throws Exception {
        mvc.perform(post("/diagnostics/orders")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("code", ""))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_ORDER"));
    }

    @Test
    void extraOrderPropertyIsSuppressed()
            throws Exception {
        mvc.perform(post("/diagnostics/orders")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("code", "O-001")
                    .param("age", "22"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("INVALID_ORDER"));
    }
}
~~~

**9 MockMvc tests** xác minh `@InitBinder("userForm")` và `@InitBinder("orderForm")` đi với đúng model attribute; `@Valid` thực sự gọi đúng validators; conversion mismatch không bị nhầm với type compatibility; những properties ngoài allowlist bị từ chối.

### Chạy tất cả tests

~~~bash
./mvnw test -Dtest=ValidatorCompatibilityTest,DiagnosticsControllerTest
~~~

Trên Windows:

~~~powershell
mvnw.cmd test -Dtest=ValidatorCompatibilityTest,DiagnosticsControllerTest
~~~

Nếu đã có Maven toàn cục có thể dùng `mvn test`. Có **25 test cases được thiết kế để pass** với Spring Boot 3.2+ và source ở trên, nhưng mã nguồn bài học **không đồng nghĩa đã chạy tests thực tế**; phải chạy trong dự án và xác nhận Surefire/JUnit results.

### Thử các endpoint bằng curl

~~~bash
curl -i -X POST "http://localhost:8080/diagnostics/users" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "displayName=Lan&age=22"

curl -i -X POST "http://localhost:8080/diagnostics/users" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "displayName=Lan&age=16"

curl -i -X POST "http://localhost:8080/diagnostics/orders" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "code=O-001"
~~~

Dự kiến các HTTP status lần lượt **200 / 400 / 200**; body tương ứng:

~~~text
USER:Lan:22
INVALID_USER
ORDER:O-001
~~~

Đây là body của **ba HTTP requests**, không phải một chương trình Java in ba dòng vào stdout. Khi có Spring Security, CSRF/authentication cần được cấu hình phù hợp; không bỏ security trong production chỉ để test pass.

## 11. Nested validator: truyền đúng object cho child validator

Nếu `CustomerForm` chứa `AddressForm address`, và `AddressValidator` chỉ hỗ trợ `AddressForm`, bạn **không thể** truyền `CustomerForm` cho AddressValidator.

~~~java
@Override
public void validate(Object target, Errors errors) {
    CustomerForm customer = (CustomerForm) target;

    AddressForm address = customer.getAddress();

    if (address == null) {
        errors.rejectValue("address", "address.required");
        return;
    }

    errors.pushNestedPath("address");
    try {
        ValidationUtils.invokeValidator(
                addressValidator, address, errors);
    }
    finally {
        errors.popNestedPath();
    }
}
~~~

Đây là snippet của `CustomerValidator` với field `addressValidator` và các model types do ứng dụng cung cấp, không phải source chạy độc lập. Cần test:

- `CustomerValidator.supports(CustomerForm.class)` true.
- `AddressValidator.supports(AddressForm.class)` true.
- Không gọi `ValidationUtils.invokeValidator(addressValidator, customer, errors)`.
- Khi `address==null`, xử lý null trước (helper yêu cầu target non-null).
- `pushNestedPath("address")`/`popNestedPath()` giúp child validator reject field `postalCode` thành `address.postalCode`.
- `finally` luôn phục hồi nested path dù validator ném exception.

Một validator hỗ trợ `CustomerForm` không tự động có nghĩa mọi nested object đều được kiểm tra. Có thể dùng composition như trên hoặc Jakarta `@Valid` cho nested property theo provider; phải test đúng cơ chế chọn dùng.

## 12. MVC, WebFlux và service validation

**Spring MVC:** `WebDataBinder` kế thừa `DataBinder`. `@InitBinder` từ controller hoặc `@ControllerAdvice` cấu hình validators. Khi `@Valid @ModelAttribute` được dùng, lỗi dữ liệu thường vào `BindingResult`; validator registration mismatch là một chuyện khác.

**Spring `@RequestBody` JSON:** Jackson deserialize JSON, rồi validation có thể chạy; `@InitBinder` vẫn có thể ảnh hưởng validator của binder, nhưng `setAllowedFields` dành cho property binding không phải JSON deserializer allowlist. JSON parse failure không được chẩn đoán thành `supports=false`.

**Spring WebFlux:** sử dụng reactive argument resolution, `WebExchangeBindException`/`HandlerMethodValidationException` tùy tình huống và `WebTestClient` thay cho MockMvc. Nguyên tắc dùng đúng validator type vẫn giữ nguyên. Không làm JDBC/network blocking trong `supports` hoặc `validate` ở reactive event loop.

**Service-layer method validation:** `@Validated`/AOP và Jakarta Bean Validation có thể ném `ConstraintViolationException`/`MethodValidationException`; chúng không phải cùng lỗi với `DataBinder#setValidator`. Đừng gộp toàn bộ thành `HTTP 400`. Một service được gọi từ scheduler hoặc event consumer có thể không có client HTTP nào để "sửa input".

## 13. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `IllegalStateException` khi `setValidator` | Binder target không được hỗ trợ. | Kiểm tra `getTarget().getClass()` và `supports`. |
| `IllegalArgumentException` từ `ValidationUtils` | Sai target truyền vào helper. | Truyền child object đúng type hoặc validator khác. |
| `ClassCastException` trong `validate` | Bypass supports hoặc supports quá rộng. | Đồng bộ check type/cast/field paths. |
| Subclass không được validate | Dùng `==` hoặc đảo `isAssignableFrom`. | Test exact/subtype, dùng đúng chiều nếu cần. |
| `Object.class` bị supports true ngoài ý muốn | Đảo chiều `clazz.isAssignableFrom(UserForm.class)`. | Dùng `UserForm.class.isAssignableFrom(clazz)`. |
| OrderForm cũng bị gắn UserFormValidator | `@InitBinder` áp dụng quá rộng. | Giới hạn theo object name và test hai routes. |
| `@Valid` nhưng không có custom errors | Validator chưa đăng ký, sai scope, hoặc only `bind`. | Kiểm tra `@InitBinder`, `getValidators()`, `validate` trigger. |
| Mất các errors từ `@NotBlank` sau chỉnh sửa | `setValidator` thay global Jakarta adapter. | Dùng `addValidators` nếu muốn kết hợp. |
| Errors bị ghi ở field không tồn tại | `rejectValue` sai property name/target. | Test target bean thật và field paths. |
| Lỗi xuất hiện muộn khi bind | Target còn null tại lúc đăng ký validator. | Test constructor binding/MVC lifecycle thực tế. |
| Dùng exclusion để che mismatch | Registration guard có thể chạy trước exclusion. | Không đăng ký wrong type. |
| Body JSON sai bị coi là lỗi supports | Sai pipeline converter. | Chẩn đoán Jackson/HttpMessageConverter riêng. |
| Trả status 400 cho lỗi validator registration | Đổ lỗi server cho client. | Giữ server error, alert và sửa cấu hình. |
| Tăng `supports` thành true với mọi class | Che mismatch cho tới khi cast/property sai. | Giới hạn đúng type/interface. |

## 14. Checklist chẩn đoán trước khi merge

- [ ] Test `supports` với exact type, subtype, unrelated type và `Object.class`.
- [ ] Nếu hỗ trợ subclass, dùng `ExpectedType.class.isAssignableFrom(clazz)` đúng chiều.
- [ ] `validate` chỉ cast/truy cập fields có ở mọi type được supports.
- [ ] Không dùng `supports` để kiểm tra business value hoặc request state.
- [ ] `@InitBinder` giới hạn đúng tên `@ModelAttribute` và không đăng ký validator cho form khác.
- [ ] Khi dùng `DataBinder` thủ công, test `bind` và `validate` như hai bước khác nhau.
- [ ] Test `setValidator`, `addValidators`, `replaceValidators` với target non-null không phù hợp.
- [ ] Test `ValidationUtils.invokeValidator` trên target đúng và sai type.
- [ ] Test `BindingResult` có field errors với dữ liệu invalid nhưng đúng type.
- [ ] Nếu có Bean Validation global, dùng `addValidators` khi cần thêm custom rules.
- [ ] Xem `getValidators()` thay vì chỉ `getValidator()` nếu binder có nhiều validators.
- [ ] Không dùng `setExcludedValidators` để che sai type ở registration.
- [ ] Kiểm tra constructor binding khi target ban đầu null.
- [ ] Viết MockMvc/WebTestClient integration tests cho các model attributes trong cùng controller.
- [ ] Không log target/rejected values hay trả stack trace chứa thông tin nội bộ.
- [ ] Đừng coi lỗi cấu hình validator là lỗi 400 mà client có thể sửa.
- [ ] Re-run tests sau khi refactor DTO class, controller method và `@InitBinder` names.

**Kết luận:** `supports() == false` chỉ ra **validator không hỗ trợ class đích**, khác với dữ liệu sai mà `validate(...)` có thể ghi qua `Errors`. Trong Spring, đăng ký validator không tương thích lên binder có target thường gây `IllegalStateException`; `ValidationUtils.invokeValidator` trên target sai thường gây `IllegalArgumentException`. Chẩn đoán đúng **type runtime, chiều `isAssignableFrom`, binder scope và lifecycle**, sau đó kiểm thử cả đăng ký lẫn thực thi sẽ ngăn các lỗi này quay lại.

## Tài liệu tham khảo

- Spring Reference — Validator interface: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Reference 6.2 — DataBinder và Jakarta Bean Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Reference 6.2 — MVC Validator configuration: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html
- Spring Reference — MVC `@InitBinder`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Javadoc 6.2 — `DataBinder`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Javadoc 6.2 — `ValidationUtils#invokeValidator`: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/ValidationUtils.html
- Spring Javadoc 6.2 — `SmartValidator`: https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/validation/SmartValidator.html

# SmartValidator và truyền gợi ý kiểm tra trong Spring Framework

## 1. Vì sao cần `SmartValidator`?

`org.springframework.validation.Validator` định nghĩa `supports(Class<?>)` và `validate(Object, Errors)`: validator xác định kiểu đối tượng được hỗ trợ và kiểm tra dữ liệu, ghi lỗi vào `Errors`. Tuy nhiên một đối tượng đôi khi cần **các bộ quy tắc khác nhau theo ngữ cảnh**. Ví dụ cùng `RegistrationForm`, khi người dùng lưu bản nháp chỉ cần email hợp lệ; khi gửi đăng ký chính thức cần thêm số điện thoại. Đó là trường hợp cần truyền gợi ý kiểm tra (validation hints).

`org.springframework.validation.SmartValidator` mở rộng `Validator`, bổ sung khả năng nhận nhiều hint: `validate(Object target, Errors errors, Object... validationHints)`. Trong ứng dụng Spring hiện đại, `SmartValidator` còn có overload dành cho `validateValue` để kiểm tra một giá trị property trong một số ngữ cảnh; phần quan trọng của bài này là `validate` với hints.

```java
public interface SmartValidator extends Validator {
    void validate(Object target, Errors errors, Object... validationHints);
}
```

Đây là chữ ký trọng tâm được rút gọn để học khái niệm; khai báo thật của interface có thể có phương thức mặc định khác tùy phiên bản Spring Framework. `Object...` là varargs nên caller có thể truyền 0, 1 hoặc nhiều hint. Hint **không phải** một danh sách lỗi, cũng không tự động biến thành quy tắc: chính implementation của validator quyết định cách hiểu.

| Khía cạnh | `Validator` | `SmartValidator` |
| --- | --- | --- |
| Kiểm tra khả năng hỗ trợ kiểu | `supports(Class<?>)` | Kế thừa `supports` |
| Validate mặc định | `validate(Object, Errors)` | Kế thừa và phải triển khai được |
| Validate có ngữ cảnh | Không có tham số hint trong giao diện cơ bản | `validate(Object, Errors, Object...)` |
| Gắn với Jakarta Bean Validation | Có thể viết validator thủ công | `LocalValidatorFactoryBean`/adapter của Spring có thể chuyển hints thành validation groups |
| Quản lý lỗi | `Errors`/`BindingResult` | Vẫn là `Errors`/`BindingResult`; hints không thay đổi hợp đồng ghi lỗi |

## 2. Gợi ý kiểm tra là gì?

Validation hint là một token do caller truyền cho validator để chọn quy tắc hoặc nhóm quy tắc. Hints có thể là `Class<?>` đại diện một **Jakarta Bean Validation group**, hoặc những object khác mà custom `SmartValidator` của ứng dụng hiểu. Không có quy định chung rằng mọi hint đều phải là class.

Ví dụ luồng xử lý:

```text
Request lưu bản nháp
    -> @Validated(Draft.class)
    -> SmartValidator.validate(form, errors, Draft.class)
    -> Chạy các quy tắc thuộc Draft

Request gửi chính thức
    -> @Validated(Submit.class)
    -> SmartValidator.validate(form, errors, Submit.class)
    -> Chạy các quy tắc thuộc Submit
```

Đây là sơ đồ khái niệm: việc Spring truyền hints phụ thuộc vào đường validation, annotation, binder và validator thực tế được cấu hình. `@Validated` của Spring hỗ trợ khai báo validation groups; `@Valid` của Jakarta dùng để kích hoạt validation mặc định, **không mang trực tiếp danh sách groups như `@Validated`**.

## 3. Ví dụ custom `SmartValidator` Java 17+

Để thấy rõ cơ chế mà không cần Jakarta Bean Validation provider, ví dụ dưới đây tự triển khai `SmartValidator` và dùng marker interfaces làm hints. Tệp `SmartValidatorDemo.java`:

```java
import java.util.Arrays;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.SmartValidator;
import org.springframework.validation.ValidationUtils;

public class SmartValidatorDemo {
    interface Draft {}
    interface Submit {}

    public static class RegistrationForm {
        private String email;
        private String phone;

        public RegistrationForm(String email, String phone) {
            this.email = email;
            this.phone = phone;
        }

        public String getEmail() { return email; }
        public void setEmail(String email) { this.email = email; }
        public String getPhone() { return phone; }
        public void setPhone(String phone) { this.phone = phone; }
    }

    public static class RegistrationValidator implements SmartValidator {
        @Override
        public boolean supports(Class<?> clazz) {
            return RegistrationForm.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            validate(target, errors, Draft.class);
        }

        @Override
        public void validate(Object target, Errors errors, Object... hints) {
            RegistrationForm form = (RegistrationForm) target;
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "email", "email.required");
            boolean submit = Arrays.asList(hints).contains(Submit.class);
            if (submit && (form.getPhone() == null
                    || form.getPhone().isBlank())) {
                errors.rejectValue("phone", "phone.required");
            }
        }
    }

    private static void run(String label, Object... hints) {
        RegistrationForm form = new RegistrationForm("user@example.com", "");
        var errors = new BeanPropertyBindingResult(form, "registrationForm");
        SmartValidator validator = new RegistrationValidator();
        validator.validate(form, errors, hints);
        System.out.println(label + ": " + errors.getErrorCount());
        System.out.println("phone error: " + errors.hasFieldErrors("phone"));
    }

    public static void main(String[] args) {
        run("draft", Draft.class);
        run("submit", Submit.class);
    }
}
```

Kết quả stdout:

```text
draft: 0
phone error: false
submit: 1
phone error: true
```

Giải thích: `supports` xác định kiểu form; phương thức `validate` cơ bản dùng chính sách mặc định là `Draft`. Overload có hints luôn kiểm tra email, và chỉ kiểm tra phone nếu có `Submit.class`. Khi gửi `Draft.class`, email hợp lệ và không cần phone. Khi gửi `Submit.class`, phone trống tạo đúng một field error.

Đoạn mã độc lập với Spring MVC và Spring Boot nhưng **cần Spring Framework JAR**. Có thể biên dịch/chạy bằng Java 17+ nếu project đã khai báo `spring-context` hoặc các module chứa `org.springframework.validation` và các dependency phù hợp. Ví dụ khi có classpath dependency được phân giải trong `SPRING_CP` trên Linux/macOS:

```bash
javac -cp "$SPRING_CP" SmartValidatorDemo.java
java -cp ".:$SPRING_CP" SmartValidatorDemo
```

Trên Windows dùng dấu `;` để ngăn cách classpath. Không chạy được bằng `javac SmartValidatorDemo.java` khi thiếu các JAR Spring.

**Lưu ý về thiết kế:** `SmartValidator` là contract, nên implementation có thể quy định default khác. Ví dụ trên cố tình coi gọi `validate(target, errors)` là chính sách `Draft`; trong ứng dụng thật, phải định nghĩa và tài liệu hóa rõ mặc định này để tránh bỏ sót ràng buộc khi caller không truyền hint.

## 4. Validation groups với Jakarta Bean Validation

Trong nhiều ứng dụng, hints là các class marker đại diện groups của Jakarta Bean Validation (`jakarta.validation.groups.Default`, các interface người dùng định nghĩa). Annotation constraint chọn group nào áp dụng.

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

interface Draft {}
interface Submit {}

public class RegistrationRequest {
    @NotBlank(groups = {Draft.class, Submit.class})
    @Email(groups = {Draft.class, Submit.class})
    private String email;

    @NotBlank(groups = Submit.class)
    private String phone;

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getPhone() { return phone; }
    public void setPhone(String phone) { this.phone = phone; }
}
```

Đây là phần mã khai báo model và groups; để biên dịch cần dependency Jakarta Validation API. Để **thực thi constraints**, cần một provider như Hibernate Validator được cấu hình. Spring Boot thường cung cấp hạ tầng khi ứng dụng khai báo starter validation phù hợp, ví dụ:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

`@Email` ở đây ràng buộc định dạng email theo provider/constraint semantics; `@NotBlank` đảm bảo có nội dung không chỉ là khoảng trắng. Một constraint không ghi rõ groups thuộc `Default`; nó **không tự động** trở thành thành viên của `Draft` hay `Submit`. Ví dụ đã khai báo groups tường minh nên kiểm tra theo đúng mục đích.

### 4.1. Dùng `@Validated` với Spring MVC

```java
import org.springframework.http.HttpStatus;
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class RegistrationController {
    @PostMapping("/registrations/draft")
    @ResponseStatus(HttpStatus.CREATED)
    String draft(@Validated(Draft.class) @ModelAttribute RegistrationRequest form,
                 BindingResult result) {
        return result.hasErrors() ? "Invalid draft" : "Draft accepted";
    }

    @PostMapping("/registrations/submit")
    String submit(@Validated(Submit.class) @ModelAttribute RegistrationRequest form,
                  BindingResult result) {
        return result.hasErrors() ? "Invalid submission" : "Submitted";
    }
}
```

Đây là **controller dùng trong ứng dụng Spring MVC đã được cấu hình** chứ không phải chương trình `main` độc lập. Khi binder sử dụng một `SmartValidator` tương thích Jakarta Bean Validation, Spring lấy validation hints từ `@Validated` để yêu cầu group tương ứng. `BindingResult` phải nằm ngay sau tham số `@ModelAttribute` để handler đọc lỗi binding/validation. `@ResponseStatus(CREATED)` trong ví dụ áp dụng cho nhánh draft cả khi trả chuỗi báo lỗi, nên nếu cần HTTP 400 cho input sai hãy trả `ResponseEntity` hoặc định nghĩa cơ chế xử lý lỗi riêng; đừng nhầm chuỗi `"Invalid draft"` với HTTP status.

Luồng ví dụ với email hợp lệ và phone rỗng:

| Request | Group | Kết quả kiểm tra |
| --- | --- | --- |
| `POST /registrations/draft` | `Draft` | Pass vì phone không bắt buộc |
| `POST /registrations/submit` | `Submit` | Lỗi `phone`, vì `@NotBlank` thuộc group `Submit` |

`@Validated` hoạt động với cơ chế validation của Spring và có thể được dùng trong nhiều ngữ cảnh. Trong Spring MVC, kết quả cụ thể còn phụ thuộc kiểu tham số (`@ModelAttribute`, `@RequestBody`, method validation), validator và phiên bản framework. Không nên suy diễn mọi trường hợp đều cho cùng exception hoặc HTTP status.

### 4.2. Gọi `SmartValidator` trực tiếp bằng groups

Trong một ứng dụng đã cấu hình `LocalValidatorFactoryBean` (adapter kết nối Jakarta Validation provider), có thể gọi:

```java
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.SmartValidator;

// validator là instance SmartValidator được cấu hình bởi Spring.
// form là RegistrationRequest đã được tạo và có giá trị.
var errors = new BeanPropertyBindingResult(form, "registrationRequest");
validator.validate(form, errors, Submit.class);
boolean invalid = errors.hasErrors();
```

Đoạn này là snippet minh họa nằm trong một method có biến `form`, `validator`; không phải chương trình độc lập. Với adapter Bean Validation phù hợp, `Submit.class` được hiểu là group. Nếu truyền một object tùy ý mà implementation không hiểu, nó có thể bị bỏ qua hoặc xử lý khác; **không có quy tắc chung** rằng mọi hint object đều là Bean Validation group.

## 5. `@Valid`, `@Validated`, `Default` và nhiều hints

| Trường hợp | Ý nghĩa |
| --- | --- |
| `@Valid` của Jakarta | Kích hoạt validation theo nhóm mặc định trong ngữ cảnh hỗ trợ; còn được dùng cho cascaded validation trên thuộc tính nested |
| `@Validated` không truyền giá trị | Kích hoạt validation với nhóm mặc định trong ngữ cảnh tương ứng |
| `@Validated(Draft.class)` | Chỉ định group `Draft` làm validation hint |
| `@Validated({Draft.class, Submit.class})` | Yêu cầu validate với nhiều groups trong một lần gọi theo semantics Bean Validation |
| Constraint không đặt `groups` | Thuộc `Default` group của Bean Validation |

Nếu chỉ kiểm tra group `Submit` thì các constraints thuộc `Default` không nhất thiết được kiểm tra. Muốn kiểm tra cả các constraints mặc định, cần khai báo group tương ứng, dùng group inheritance hoặc group sequence theo yêu cầu. Việc truyền nhiều groups **không tự tạo thứ tự** bắt buộc; nếu cần thứ tự và dừng theo nhóm lỗi, hãy sử dụng `@GroupSequence` theo Jakarta Bean Validation, đồng thời xem xét các giới hạn của group sequence.

Ví dụ:

```java
interface Draft {}
interface Submit extends Draft {}
```

Với quan hệ kế thừa group trên, validate group `Submit` theo Jakarta Bean Validation sẽ bao gồm constraints được khai báo cho group cha `Draft`, ngoài constraints của `Submit` (theo quy tắc kế thừa groups). Đây là cách chủ động mô hình hóa chính sách; không phải cứ đặt hai interface gần nhau là framework tự hiểu quan hệ.

### 5.1. Validation hints khác với validation data

Giả sử hai request có cùng class nhưng age khác nhau. `supports(RegistrationRequest.class)` cho cùng kết quả; `@Validated(Submit.class)` chọn **bộ ràng buộc**; `validate` mới đọc **giá trị hiện tại** để quyết định lỗi. Không đưa logic kiểm tra từng giá trị vào `supports` và cũng không dùng hints để truyền dữ liệu nghiệp vụ cần bind.

## 6. Hints đi qua Spring `DataBinder` như thế nào?

`DataBinder` cho phép đăng ký một hoặc nhiều validators và kích hoạt validation. Với `SmartValidator`, binder có thể chuyển tiếp hints vào overload tương ứng.

```java
import org.springframework.validation.DataBinder;
import org.springframework.validation.SmartValidator;

// `form` và `smartValidator` đã được khởi tạo; đoạn mã trong method.
DataBinder binder = new DataBinder(form, "registrationForm");
binder.setValidator(smartValidator);
binder.validate(Submit.class);
boolean hasErrors = binder.getBindingResult().hasErrors();
```

Khi gọi `binder.validate(Submit.class)`, binder chuyển hints cho các `SmartValidator` được đăng ký. Với validator chỉ triển khai interface `Validator`, lời gọi không có overload hints tương ứng; binder có thể gọi phương thức thường và không áp dụng hints theo cách custom `SmartValidator` mong đợi. Cần kiểm tra implementation và cách cấu hình thực tế.

**Đăng ký không bằng kích hoạt:** `binder.setValidator(...)` hoặc `binder.addValidators(...)` thiết lập validator; việc validate chỉ diễn ra khi code/binder/handler thực hiện validation. Với controller, annotation như `@Validated` thường yêu cầu binder thực hiện bước đó. Nếu tự tạo `DataBinder`, hãy chủ động gọi `validate`.

### 6.1. `@InitBinder` và phạm vi đăng ký

```java
import org.springframework.validation.SmartValidator;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

// Trong controller có field smartValidator đã inject:
@InitBinder("registrationRequest")
void initBinder(WebDataBinder binder) {
    binder.addValidators(smartValidator);
}
```

`@InitBinder("registrationRequest")` giới hạn binder theo tên model attribute, tránh đăng ký validator hẹp cho các object không tương thích. Khi dùng `@Validated(Submit.class)` với tham số có tên model phù hợp, framework có thể gọi `SmartValidator` bằng hint group. Nếu validator đang được đăng ký không `supports` kiểu target, Spring có thể từ chối ở bước thêm/chọn validator tùy API và đường thực thi; hãy bảo đảm kiểu hỗ trợ khớp model.

## 7. Thực hành lỗi, kiểm thử và thiết kế group

### 7.1. Những lỗi thường gặp

- **Chỉ implements `Validator` rồi mong nhận được hints:** cần `SmartValidator` (hoặc adapter hỗ trợ) để xử lý nhóm có ngữ cảnh qua overload.
- **Quên triển khai `validate(Object, Errors)` của interface cha:** custom `SmartValidator` vẫn cần quyết định quy tắc mặc định cho phương thức này.
- **Nhầm `supports` với hints:** `supports` kiểm tra type; hints chọn chính sách/rule set.
- **Bỏ `Default` ngoài ý muốn:** constraint không khai báo groups thuộc Default và có thể không chạy khi chỉ validate group khác.
- **Dùng `@Validated` mà thiếu provider:** annotation không biến constraint thành logic thực thi khi không có validator/provider phù hợp.
- **Đặt `BindingResult` sai vị trí:** đối với binding/validation model, phải đặt ngay sau tham số tương ứng.
- **Cho rằng nhiều groups chạy tuần tự:** khi cần thứ tự chính thức, dùng group sequence của Bean Validation.
- **Gắn validator hẹp cho mọi binder:** chỉ đăng ký vào đúng target hoặc kiểm tra `supports` trước khi thực thi.
- **Trộn lỗi chuyển đổi và lỗi ràng buộc:** request chứa `age=xyz` có thể gây `typeMismatch` trước khi group validation kiểm tra điều kiện tuổi; hai lỗi cần được phân biệt.

### 7.2. Những ca kiểm thử nên có

1. Cùng một form, validate với `Draft` pass nhưng `Submit` fail ở trường chỉ bắt buộc khi submit.
2. Validate không truyền hint: xác minh nhóm mặc định mà custom `SmartValidator` tự quy định.
3. Validate nhiều hints: biết rõ rule nào được gọi, nhất là khi dùng Jakarta Bean Validation groups.
4. Validate target không được hỗ trợ: kiểm tra `supports` và cách đăng ký, không gọi method rồi phụ thuộc vào `ClassCastException`.
5. Kiểm thử Spring MVC cả `@ModelAttribute` và `@RequestBody` nếu ứng dụng hỗ trợ cả hai; kiểm tra `BindingResult`, exceptions, HTTP status tùy trường hợp.
6. Kiểm thử nested constraints và group inheritance/group sequence nếu bài toán thực sự cần.

### 7.3. Quy tắc thiết kế groups

Đặt tên group theo **ngữ cảnh nghiệp vụ** (ví dụ `Draft`, `Submit`) thay vì theo loại màn hình giao diện ngẫu nhiên. Hạn chế tạo quá nhiều group chồng chéo khiến developer không biết constraint nào được áp dụng. Cấu hình group nên được kiểm thử như contract API: đổi annotation group có thể thay đổi tính hợp lệ của request ngay cả khi Java field không đổi.

## 8. Tổng kết

`SmartValidator` bổ sung khả năng truyền `Object... validationHints` cho Spring `Validator`, giúp một mô hình dữ liệu được kiểm tra theo ngữ cảnh. Custom validator có thể định nghĩa cách hiểu hints, còn khi kết hợp `LocalValidatorFactoryBean` với Jakarta Bean Validation, hints dạng `Class<?>` thường đại diện cho validation groups. Trong Spring MVC, `@Validated` đưa group từ điểm nhận request vào luồng validation; `DataBinder` và `Errors` tiếp tục đảm nhiệm thực thi và ghi lỗi. Muốn hệ thống đáng tin, hãy xác định rõ group mặc định, phạm vi validator, vị trí `BindingResult` và các tình huống lỗi binding.

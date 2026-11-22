# Kích hoạt validator sau bước binding trong Spring MVC

## 1. Vì sao cần validation sau binding?

Khi nhận một HTTP request, Spring MVC có thể lấy dữ liệu dạng chuỗi từ form/query/path/header, chuyển đổi kiểu và gán vào đối tượng Java. Công đoạn đó gọi là **data binding**. Binding trả lời câu hỏi “Dữ liệu từ request có thể đưa vào đối tượng này không?”, còn **validation** trả lời “Đối tượng sau khi có dữ liệu có thỏa các quy tắc hay không?”.

Ví dụ form gửi `age=17`: chuyển chuỗi `"17"` thành `Integer` thành công, nhưng yêu cầu nghiệp vụ “tuổi từ 18” không đạt. Ngược lại, `age=abc` có thể gây lỗi chuyển kiểu ngay trong binding, trước khi xét quy tắc `@Min(18)`. Cả hai nhóm lỗi có thể được lưu trong `BindingResult` để tầng controller xử lý.

Mấu chốt là **đăng ký validator** và **kích hoạt validator** là hai việc khác nhau. `@InitBinder` dùng để cấu hình `WebDataBinder` (bao gồm gắn validator) **trước khi bind**; `@Valid`, `@Validated` hoặc lệnh `binder.validate()` yêu cầu chạy validation **sau khi dữ liệu đã được bind**.

## 2. Vị trí của validation trong vòng đời request

Với tham số `@ModelAttribute` ở Spring MVC, có thể hình dung luồng cơ bản như sau:

~~~text
HTTP request
    │
    ▼
Spring MVC chọn handler/controller
    │
    ▼
Tạo hoặc lấy model attribute; tạo WebDataBinder
    │
    ├── Chạy @InitBinder để cấu hình converter, allowedFields, validator...
    │
    ▼
Bind request values vào đối tượng
    ├── Chuyển kiểu, gán constructor/property
    └── Ghi lỗi binding (ví dụ typeMismatch) vào BindingResult
    │
    ▼
Có @Valid / @Validated trên tham số?
    ├── Có  → gọi các validator phù hợp, bổ sung lỗi validation
    └── Không → không tự chạy Bean Validation cho tham số đó
    │
    ▼
BindingResult chứa kết quả binding + validation
    ├── Có BindingResult/Errors ngay sau tham số → controller tự xử lý
    └── Không → lỗi có thể được Spring chuyển thành ngoại lệ
~~~

Các điểm cần phân biệt:

1. **Binding luôn đi trước validation của đối tượng** trong luồng `@ModelAttribute` thông thường; validator nhận được đối tượng đã qua bước chuyển kiểu/gán dữ liệu.
2. `@InitBinder` chạy ở giai đoạn **chuẩn bị binder**, không phải một callback “sau binding”. Đặt `binder.addValidators(...)` trong đó để khai báo bộ kiểm tra sẽ được sử dụng về sau.
3. `BindingResult` tập hợp `FieldError`/`ObjectError`, bao gồm lỗi chuyển kiểu và lỗi quy tắc; gọi `hasErrors()` để quyết định có tiếp tục hay không.
4. Spring tạo binder riêng cho từng lần xử lý đối tượng/request phù hợp; không nên giữ `WebDataBinder` làm trạng thái dùng chung giữa các request.

## 3. Cách thông dụng: `@Valid` sau `@ModelAttribute` binding

Ví dụ dưới đây dành cho **Spring Framework 6.x / Spring Boot 3.x, Java 17+**, dùng Jakarta Bean Validation. Trong một dự án Spring Boot MVC, cần có cả MVC starter và validation provider:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Nếu dùng Spring MVC độc lập thay vì Boot, cần cấu hình Bean Validation provider tương ứng. Khi Bean Validation có trên classpath, Spring MVC thường đăng ký `LocalValidatorFactoryBean` làm validator mặc định phục vụ `@Valid` và `@Validated`.

**DTO nhận dữ liệu form**, tệp `RegistrationForm.java`:

~~~java
package com.example.demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record RegistrationForm(
        @NotBlank(message = "Tên đăng nhập không được để trống")
        String username,

        @NotBlank @Email
        String email,

        @NotNull @Min(18)
        Integer age
) {}
~~~

Record hoạt động với constructor binding được hỗ trợ trong Spring MVC 6.x. Có thể thay bằng JavaBean với constructor rỗng và getter/setter khi dùng property binding. Chú ý `@Min(18)` tự nó không bắt buộc giá trị khác `null`, nên `@NotNull` cũng cần thiết nếu trường tuổi bắt buộc.

**Controller**, tệp `RegistrationController.java`:

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.validation.BindingResult;

import java.util.Map;

@RestController
public class RegistrationController {

    @PostMapping(
            path = "/registrations",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> register(
            @Valid @ModelAttribute("form") RegistrationForm form,
            BindingResult errors
    ) {
        if (errors.hasErrors()) {
            var details = errors.getFieldErrors().stream()
                    .map(e -> e.getField() + ": " + e.getDefaultMessage())
                    .toList();
            return ResponseEntity.badRequest()
                    .body(Map.of("errors", details));
        }

        return ResponseEntity.ok(Map.of("status", "accepted"));
    }
}
~~~

Ở đây, Spring lấy `username`, `email` và `age` từ form, bind vào `RegistrationForm`, rồi thấy `@Valid` nên gọi Bean Validation. `BindingResult errors` **phải đứng ngay sau** tham số được validate để controller nhận lỗi của đúng đối tượng. Nếu lỗi tồn tại, controller tự trả HTTP 400; nếu hợp lệ, trả HTTP 200. Đoạn mã giả định ứng dụng Boot đã có lớp `@SpringBootApplication` để khởi chạy.

Thử request lỗi:

~~~bash
curl -i -X POST http://localhost:8080/registrations -H "Content-Type: application/x-www-form-urlencoded" --data "username=&email=bad-email&age=17"
~~~

Kết quả mong đợi là **400 Bad Request**, với các lỗi liên quan đến username trống, email sai định dạng và tuổi nhỏ hơn 18. **Không nên phụ thuộc thứ tự lỗi hoặc chính xác ngôn ngữ thông báo** vì chúng chịu ảnh hưởng từ Bean Validation provider và cấu hình message/locale. Một request hợp lệ như sau sẽ nhận phản hồi chứa `{"status":"accepted"}`:

~~~bash
curl -i -X POST http://localhost:8080/registrations -H "Content-Type: application/x-www-form-urlencoded" --data "username=linh&email=linh%40example.com&age=22"
~~~

Điều gì kích hoạt việc chạy validator? Chính `@Valid` gắn trên **tham số handler**. Chỉ thêm `@NotBlank`, `@Email` vào DTO mà không gắn `@Valid`/`@Validated` tại điểm xử lý request thì không bảo đảm validation của DTO sẽ tự chạy.

## 4. `@Validated` và nhóm kiểm tra

`@Validated` của Spring cũng kích hoạt validation khi đặt trên tham số `@ModelAttribute`, đồng thời cho phép truyền **validation groups**. Ví dụ khi tạo mới, tên đăng nhập là bắt buộc:

~~~java
package com.example.demo;

public interface OnCreate {}
~~~

~~~java
package com.example.demo;

import jakarta.validation.constraints.NotBlank;

public record AccountForm(
        @NotBlank(groups = OnCreate.class) String username
) {}
~~~

~~~java
@PostMapping("/accounts")
public ResponseEntity<?> create(
        @Validated(OnCreate.class) @ModelAttribute AccountForm form,
        BindingResult errors
) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Thông tin không hợp lệ");
    }
    return ResponseEntity.ok("created");
}
~~~

Đoạn handler này là **phần trích** trong một controller đã có import `org.springframework.validation.annotation.Validated`, `BindingResult` và các annotation MVC liên quan. `@Validated(OnCreate.class)` chọn nhóm `OnCreate`. Ràng buộc chỉ thuộc nhóm `Default` không tự động được kiểm tra trong lần gọi chỉ chọn `OnCreate`; muốn kiểm tra nhiều nhóm, phải chỉ định hoặc thiết kế quan hệ nhóm phù hợp.

Ở mức controller, tránh nhầm `@Validated` trên **tham số DTO** với `@Validated` trên **class controller** (cách kích hoạt method validation dựa trên AOP ở các cấu hình/phiên bản nhất định). Với Spring MVC 6.1+, framework còn hỗ trợ method validation trực tiếp cho ràng buộc đặt trên các tham số phương thức, nên cơ chế ngoại lệ có thể khác validation riêng một DTO.

## 5. Kết hợp Bean Validation với một Spring `Validator` tùy chỉnh

Khi quy tắc khó diễn đạt bằng annotation có sẵn, có thể viết `org.springframework.validation.Validator`. Ví dụ không cho phép username “admin”. Tệp `UsernameRuleValidator.java`:

~~~java
package com.example.demo;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class UsernameRuleValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return RegistrationForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationForm form = (RegistrationForm) target;
        if ("admin".equalsIgnoreCase(form.username())) {
            errors.rejectValue(
                    "username",
                    "username.reserved",
                    "Tên đăng nhập này đã được dành riêng"
            );
        }
    }
}
~~~

Đăng ký trong `RegistrationController` bằng constructor injection và một phương thức `@InitBinder`:

~~~java
private final UsernameRuleValidator usernameRuleValidator;

public RegistrationController(UsernameRuleValidator usernameRuleValidator) {
    this.usernameRuleValidator = usernameRuleValidator;
}

@InitBinder("form")
void configureBinder(WebDataBinder binder) {
    binder.addValidators(usernameRuleValidator);
}
~~~

Đây cũng là **đoạn bổ sung trong controller**, với import `org.springframework.web.bind.annotation.InitBinder` và `org.springframework.web.bind.WebDataBinder`. Vì handler đã khai báo `@ModelAttribute("form")`, `@InitBinder("form")` áp dụng đúng binder của attribute đó.

Khi nhận form, Spring sẽ:

- tạo/cấu hình binder và thêm `UsernameRuleValidator`;
- bind dữ liệu request;
- gặp `@Valid`, chạy các validator liên quan (validator Bean Validation và validator bổ sung);
- gom các lỗi vào cùng `BindingResult`. Với `username=admin`, mã lỗi `username.reserved` được gắn cho field `username`.

Ưu tiên `addValidators(...)` nếu muốn bổ sung quy tắc, vì `setValidator(...)` thay validator hiện có trên binder và có thể làm mất các ràng buộc annotation nếu không chủ định cấu hình lại. `supports(Class<?>)` phải trả `true` cho kiểu đối tượng đích; đăng ký một validator không hỗ trợ kiểu dữ liệu có thể làm binder từ chối cấu hình.

Nếu quy tắc dùng chung cho nhiều controller, có thể dùng `@ControllerAdvice` với `@InitBinder`; nếu cần thay validator mặc định toàn MVC, có thể cấu hình `WebMvcConfigurer#getValidator()`. Chọn phạm vi nhỏ nhất đáp ứng yêu cầu.

## 6. Thấy rõ trình tự bằng `DataBinder` thuần Spring

Ngoài MVC, `DataBinder` cũng thể hiện rõ việc **bind không tự đồng nghĩa validate**. Ví dụ hoàn chỉnh dưới đây dùng Spring `spring-context`/`spring-beans` có sẵn trên classpath dự án:

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class DataBinderSequenceDemo {

    public static class Order {
        private int quantity;

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }
    }

    public static class OrderValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Order.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Order order = (Order) target;
            if (order.getQuantity() <= 0) {
                errors.rejectValue(
                        "quantity", "quantity.positive",
                        "Số lượng phải lớn hơn 0"
                );
            }
        }
    }

    public static void main(String[] args) {
        Order order = new Order();
        DataBinder binder = new DataBinder(order);
        binder.addValidators(new OrderValidator());

        binder.bind(new MutablePropertyValues(Map.of("quantity", "0")));
        System.out.println("Sau binding: " +
                binder.getBindingResult().getErrorCount());

        binder.validate();
        System.out.println("Sau validation: " +
                binder.getBindingResult().getErrorCount());
        System.out.println(
                binder.getBindingResult()
                        .getFieldError("quantity")
                        .getDefaultMessage()
        );
    }
}
~~~

Khi chạy phương thức `main` trong một Java 17+ project có các thư viện Spring nêu trên, stdout là:

~~~text
Sau binding: 0
Sau validation: 1
Số lượng phải lớn hơn 0
~~~

Ở đây, `quantity="0"` đã chuyển thành `int 0` thành công nên không sinh lỗi binding; `validate()` mới tạo lỗi nghiệp vụ. Ví dụ gọi `binder.validate()` minh bạch vì không có MVC controller và annotation để tự kích hoạt. Trong MVC đã dùng `@Valid`, thông thường **không cần gọi validate lần hai**.

## 7. Khác biệt khi dùng `@RequestBody` (JSON)

Với form/query + `@ModelAttribute`, Spring thực hiện binding vào model attribute qua `WebDataBinder`. Còn với JSON + `@RequestBody`, `HttpMessageConverter` (thường là Jackson) **deserialize** JSON thành đối tượng trước; sau đó Spring vẫn có thể dùng binder/validator để kiểm tra đối tượng nếu tham số có `@Valid` hoặc `@Validated`.

~~~java
@PostMapping(path = "/api/registrations",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> registerJson(
        @Valid @RequestBody RegistrationForm request
) {
    return ResponseEntity.ok(Map.of("status", "accepted"));
}
~~~

Đây là đoạn handler trích từ controller, dùng lại DTO và các import phù hợp. Nếu JSON hợp cú pháp nhưng vi phạm ràng buộc của DTO, Spring MVC thường phát sinh `MethodArgumentNotValidException` khi không có tham số `BindingResult` xử lý cục bộ. Nếu JSON sai cú pháp/không deserialize được, lỗi là ở **bước đọc body**, điển hình `HttpMessageNotReadableException`; đây chưa phải lỗi validation theo `@Min`/`@Email`.

Với Spring MVC 6.1+, nếu handler có các ràng buộc Jakarta trực tiếp trên tham số phương thức (ví dụ `@Min` trên `@RequestParam`), **method validation** có thể được áp dụng và phát sinh `HandlerMethodValidationException`. Khi xây dựng API lỗi tập trung, cần xét cả hai loại ngoại lệ trên; đừng mặc định mọi lỗi đều là `MethodArgumentNotValidException`.

## 8. Xử lý lỗi đúng và lưu ý vận hành

| Tình huống | Nơi phát sinh / cách xử lý |
| --- | --- |
| `age=abc` khi đích là `Integer` | Lỗi conversion/binding, thường có mã `typeMismatch`; xem `BindingResult`. |
| `age=17` với `@Min(18)` | Binding thành công, validator thêm lỗi ràng buộc. |
| `@Valid @ModelAttribute ... , BindingResult errors` | Validation được kích hoạt; controller nhận lỗi vì `BindingResult` đứng liền sau. |
| `@Valid` nhưng không có `BindingResult` liền sau | Lỗi validation thường được đưa thành ngoại lệ MVC, mặc định có thể phản hồi 400. |
| Có Spring `Validator` trong `@InitBinder` nhưng không có `@Valid`/`@Validated` | Validator đã đăng ký, **chưa được yêu cầu chạy** cho tham số đó. |
| `@RequestBody` chứa JSON hỏng | Lỗi đọc/deserialization body xảy ra trước khi kiểm tra Bean Validation. |

Để xử lý lỗi có kiểm soát:

1. Trên form MVC cần trả lại view kèm thông báo, đặt `BindingResult` liền sau đối tượng và dùng `hasFieldErrors(...)`, `getFieldErrors()` hoặc `getAllErrors()`.
2. Trên REST API, có thể xử lý lỗi cục bộ bằng `BindingResult` (khi chữ ký method hỗ trợ), hoặc dùng `@RestControllerAdvice` để chuyển ngoại lệ thành body lỗi nhất quán.
3. Phân biệt mã lỗi (`typeMismatch`, `NotBlank`, mã tùy chỉnh) với thông điệp hiển thị; thông điệp có thể thay đổi theo locale và `MessageSource`.
4. Sử dụng DTO chuyên biệt cho HTTP input và chỉ cho phép các trường có chủ đích được bind. Validation kiểm tra giá trị, **không thay thế** chính sách cho phép field hoặc kiểm tra phân quyền.
5. Không xử lý lỗi bằng cách chỉ gọi `errors.clear()` hoặc bỏ qua `hasErrors()`: dữ liệu sau binding có thể chưa hợp lệ để chuyển cho tầng nghiệp vụ.

## 9. Lỗi thường gặp và cách tự kiểm tra

**Nhầm thứ tự:** Viết logic validate trong `@InitBinder` rồi kỳ vọng form đã có dữ liệu. `@InitBinder` chủ yếu dùng chuẩn bị bộ chuyển đổi, allowed fields và validator; validation thực tế diễn ra sau bước bind khi có trigger.

**Thiếu provider:** Dùng `@Valid` và các annotation constraint nhưng không có Jakarta Bean Validation provider. Trên Spring Boot 3, kiểm tra dependency `spring-boot-starter-validation` và import `jakarta.validation.*`; các ví dụ cũ dùng `javax.validation.*` dành cho thế hệ Spring/Boot trước.

**Đặt `BindingResult` sai chỗ:** `BindingResult` phải ngay sau tham số nó mô tả, không đặt một tham số không liên quan chen giữa. Nếu có nhiều đối tượng được bind/validate, mỗi `BindingResult` cần đứng cạnh đúng đối tượng.

**Quên trigger:** Chỉ thêm `@InitBinder` hoặc `Validator` chưa đủ; trên handler, dùng `@Valid`/`@Validated`. Nếu tự sử dụng `DataBinder`, gọi `validate()` sau `bind(...)`.

**Sai nhóm validation:** `@Validated(Create.class)` không tự kiểm tra toàn bộ constraint thuộc nhóm `Default`. Thiết kế group và thử cả request hợp lệ lẫn bất hợp lệ.

**Nhầm lỗi binding với validation:** Nếu giá trị đầu vào không thể chuyển kiểu, kiểm tra `FieldError#isBindingFailure()` và mã lỗi trước khi kết luận validator hoạt động sai. Một `BindingResult` có thể chứa đồng thời cả hai nhóm lỗi.

Có thể kiểm thử bằng `MockMvc`: gửi form hợp lệ và đòi HTTP 200; gửi `age=17`, `username=admin` và đòi 400; gửi `age=abc` để xác minh lỗi conversion; bỏ `@Valid` trong một thí nghiệm tách biệt sẽ cho thấy quy tắc Bean Validation không còn tự chạy trên tham số. Với ví dụ `@InitBinder`, đảm bảo `username=admin` đi vào `UsernameRuleValidator` sau khi bind.

## 10. Ghi nhớ

Trong Spring MVC, **binding tạo ra đối tượng từ request, validation kiểm tra đối tượng đó**. `@InitBinder` đăng ký cấu hình và validator trước binding; `@Valid`/`@Validated` là tín hiệu thường dùng để chạy validator sau binding; `BindingResult` là nơi đọc tập lỗi được tích lũy. Nắm rõ ba vai trò này giúp phân biệt lỗi chuyển kiểu, lỗi quy tắc và lỗi ở khâu đọc request, đồng thời tránh chạy thiếu hoặc chạy trùng validation.

Tài liệu chính thức để tra cứu thêm:

- [Spring MVC — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC — Cấu hình Validator](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html)
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)

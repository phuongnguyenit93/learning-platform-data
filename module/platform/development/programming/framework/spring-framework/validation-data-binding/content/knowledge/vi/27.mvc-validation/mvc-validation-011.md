# Validator cục bộ, validator toàn cục và nhiều bộ kiểm tra trong Spring MVC

## 1. Bài toán: một form có nhiều loại quy tắc kiểm tra

Trong Spring MVC, việc nhận dữ liệu HTTP và việc xác nhận dữ liệu hợp lệ là hai bước liên quan nhưng không đồng nhất. Ví dụ, một form đăng ký có các điều kiện:

- `username` không được để trống theo Jakarta Bean Validation `@NotBlank`.
- `age` phải ít nhất 18 theo `@Min(18)`.
- Tên `admin` bị dành riêng theo quy tắc của ứng dụng.
- Không nhận email thuộc miền `blocked.test` theo chính sách riêng của hệ thống.

Hai điều đầu có thể đặt trực tiếp trong DTO bằng các constraint Jakarta. Hai điều sau có thể cài bằng một hay nhiều `org.springframework.validation.Validator` của Spring.

**Câu hỏi trọng tâm:** Làm sao Spring MVC cùng sử dụng validator mặc định trên toàn ứng dụng và nhiều validator riêng cho một form/controller mà không vô tình làm mất kiểm tra `@NotBlank`, `@Min`?

Câu trả lời nằm ở ba khái niệm:

1. **Validator toàn cục** được cấu hình cho hạ tầng Spring MVC, thường là `LocalValidatorFactoryBean` khi có Jakarta Bean Validation provider.
2. **Validator cục bộ** được thêm vào `WebDataBinder` của một controller hoặc một model attribute qua `@InitBinder`.
3. **Nhiều bộ kiểm tra** có thể cùng tham gia một lượt validation khi binder dùng `addValidators(...)`, thay vì thay thế toàn bộ danh sách.

Phạm vi bài này là **Spring MVC Servlet stack** (Spring Framework 6.x, Spring Boot 3.x). Spring WebFlux có API tương tự nhưng hạ tầng xử lý request khác. Không đánh đồng cơ chế này với method validation trên Spring AOP service hay toàn bộ Jakarta Bean Validation.

## 2. Hai giao diện Validator và vai trò của chúng

### 2.1. Spring Validator

Spring có giao diện:

```java
package org.springframework.validation;

public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

Đây là **chữ ký API minh họa**, không phải file bạn tự viết. Trong ứng dụng, import interface có sẵn từ Spring.

- `supports(Class<?>)`: khai báo validator có thể xử lý loại object nào. Với DTO `SignupForm`, có thể trả `SignupForm.class.isAssignableFrom(clazz)`.
- `validate(Object, Errors)`: đánh giá dữ liệu và **ghi lỗi** bằng `errors.rejectValue(...)` cho field hoặc `errors.reject(...)` cho lỗi mức object.

Khác `jakarta.validation.ConstraintValidator<A,T>`, Spring `Validator` **không trả boolean valid/invalid**. Nó thêm các `ObjectError`/`FieldError` vào một đối tượng `Errors` đang được dùng.

Ví dụ validator tên người dùng:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class UsernameRuleValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        if ("admin".equalsIgnoreCase(form.getUsername())) {
            errors.rejectValue(
                "username", "reservedUsername",
                "Tên này được dành riêng");
        }
    }
}
```

Đây là **đoạn minh họa** cần `SignupForm` tương ứng. Chương trình hoàn chỉnh ở mục 6 sẽ có toàn bộ file, import và cấu hình.

### 2.2. Jakarta Bean Validation và LocalValidatorFactoryBean

Jakarta Bean Validation dùng các annotation như `@NotNull`, `@NotBlank`, `@Min`, `@Email`, `@Size`; provider phổ biến là Hibernate Validator. Cơ chế này được kết nối vào Spring MVC qua `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean`, là cầu nối hỗ trợ **Spring `Validator`/`SmartValidator`** và **Jakarta `Validator`**.

Khi thư viện Bean Validation có mặt, Spring MVC thông thường tự đăng ký `LocalValidatorFactoryBean` làm validator toàn cục để xử lý `@Valid` và `@Validated` trên controller method arguments.

Vì thế trong ứng dụng Spring Boot đã có `spring-boot-starter-validation`, **không cần tự thay global validator chỉ để thêm một quy tắc riêng cho một form**. Dùng `@InitBinder(...).addValidators(...)` thường đơn giản và ít tác dụng phụ hơn.

### 2.3. Spring SmartValidator

`org.springframework.validation.SmartValidator` mở rộng Spring `Validator`, có thêm kiểu gọi hỗ trợ *validation hints* (ví dụ validation groups):

```java
// Chữ ký minh họa trong API Spring:
void validate(Object target, Errors errors, Object... validationHints);
```

`LocalValidatorFactoryBean` hỗ trợ cơ chế này. Khi controller dùng `@Validated(SomeGroup.class)`, các group có thể được chuyển qua hints cho `SmartValidator`. Một custom `Validator` đơn giản chỉ cài `validate(Object, Errors)` không tự đọc và lọc validation groups như một Bean Validation provider; nếu cần phân chia group, phải thiết kế riêng hoặc dùng API phù hợp.

## 3. Validator toàn cục của Spring MVC

### 3.1. Mặc định

Khi Spring MVC tìm thấy Jakarta Validation provider, nó đăng ký validator tích hợp để hỗ trợ DTO validation. Ví dụ:

```java
public class SignupForm {

    @NotBlank
    private String username;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    // Constructor mặc định, getters và setters...
}
```

Một controller dùng:

```java
@PostMapping("/signup")
public ResponseEntity<?> signup(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid form");
    }
    return ResponseEntity.ok().build();
}
```

Khi `@Valid` kích hoạt validation, validator MVC toàn cục có thể tạo `FieldError` từ `@NotBlank`, `@Email`, `@NotNull` hoặc `@Min`. Đó là **validation trên object đã bind**, không nhất thiết là executable method validation trên tham số scalar của controller.

### 3.2. Tùy chỉnh qua WebMvcConfigurer#getValidator()

Trong ứng dụng cần tự chọn validator dùng chung cho MVC, Spring cung cấp hook:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.Validator;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcValidationConfig implements WebMvcConfigurer {

    private final Validator myMvcValidator;

    public MvcValidationConfig(Validator myMvcValidator) {
        this.myMvcValidator = myMvcValidator;
    }

    @Override
    public Validator getValidator() {
        return myMvcValidator;
    }
}
```

**Đây là cấu hình minh họa, không dùng chung với ví dụ chạy ở mục 6.** `myMvcValidator` phải là bean được tạo phù hợp và không gây vòng phụ thuộc trong cấu hình. Khi bạn trả về một validator riêng từ `getValidator()`, nó thay thế lựa chọn mặc định cho **hạ tầng MVC**. Nếu validator ấy không tích hợp Jakarta Bean Validation, đừng kỳ vọng các annotation `@NotBlank`, `@Min` tiếp tục được đánh giá chỉ vì chúng vẫn nằm trên DTO.

Có thể dùng `LocalValidatorFactoryBean` hoặc một chiến lược kết hợp phù hợp làm validator toàn cục nếu cần giữ cả Bean Validation và logic bổ sung. Tuy nhiên, **để thêm logic cho một DTO cụ thể**, cách an toàn hơn thường là giữ cấu hình MVC mặc định và thêm validator local.

**“Toàn cục” ở đây là toàn cục trong phạm vi MVC argument validation**, không tự động có nghĩa mọi lời gọi Java, service, scheduled task hoặc message consumer đều sử dụng đúng cùng cấu hình. Method validation qua Spring AOP và MVC built-in method validation còn có điểm tích hợp riêng cần kiểm tra.

## 4. Validator cục bộ: @InitBinder và WebDataBinder

Một controller có thể định nghĩa phương thức `@InitBinder` để điều chỉnh binder trước bước binding/validation.

```java
@RestController
public class SignupController {

    private final UsernameRuleValidator usernameValidator;

    public SignupController(UsernameRuleValidator usernameValidator) {
        this.usernameValidator = usernameValidator;
    }

    @InitBinder("signup")
    void initBinder(WebDataBinder binder) {
        binder.addValidators(usernameValidator);
    }

    @PostMapping("/signup")
    public String create(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult errors) {
        return errors.hasErrors() ? "INVALID" : "ACCEPT";
    }
}
```

Đây là **đoạn tích hợp minh họa**; cần import, DTO và khai báo bean validator tương ứng.

Ý nghĩa từng phần:

- `@InitBinder("signup")` chỉ áp dụng cho binder thuộc model attribute có tên `signup`. Nó không mặc nhiên áp dụng cho mọi bean của ứng dụng.
- `WebDataBinder` là binder đang xử lý một đối tượng cụ thể trong request; cấu hình này diễn ra trước khi validate.
- `addValidators(usernameValidator)` **bổ sung** validator vào danh sách có sẵn, thay vì thay thế validator toàn cục.
- `@Valid` trên đối tượng được bind làm Spring MVC yêu cầu validate form.
- `BindingResult` phải đứng **ngay sau** tham số được bind; controller tự quyết định trả lỗi hay tiếp tục nghiệp vụ.

Nếu `@InitBinder` được định nghĩa trong chính `@Controller`, tác động mặc định là cục bộ với controller đó. Nếu khai báo trong `@ControllerAdvice`, có thể áp dụng cho nhiều controller tùy selector của advice; thêm tên attribute trong `@InitBinder("signup")` sẽ giới hạn binder tương ứng.

**Không phải cứ khai báo `@InitBinder` là validation chạy ngay.** Nó là điểm cấu hình binder. Validation thường được kích hoạt khi có `@Valid`/`@Validated`, hoặc khi ứng dụng gọi binder/validator chủ động.

## 5. addValidators(), setValidator() và replaceValidators(): không giống nhau

Đây là sự khác biệt quyết định việc một ứng dụng **giữ hay mất validator mặc định**.

| API của DataBinder/WebDataBinder | Hành vi |
| --- | --- |
| `setValidator(validator)` | **Xóa danh sách validator hiện tại**, rồi đặt một validator mới; nếu `null` có thể xóa toàn bộ |
| `addValidators(v1, v2)` | **Thêm** vào danh sách hiện tại, giữ các validator đã có |
| `replaceValidators(v1, v2)` | Xóa danh sách cũ và **thay bằng danh sách được cung cấp** |
| `getValidator()` | Trả validator đầu tiên (primary) nếu có |
| `getValidators()` | Trả danh sách validator đã đăng ký |
| `getValidatorsToApply()` | Danh sách sẽ thực sự được dùng sau khi áp dụng bộ lọc loại trừ (API từ Spring 6.1) |

Trong `@InitBinder`:

```java
// Khuyến nghị nếu muốn giữ Bean Validation mặc định và cộng thêm rule.
binder.addValidators(usernameValidator, emailValidator);
```

So với:

```java
// Cẩn trọng: thay thế danh sách hiện có.
binder.setValidator(usernameValidator);
```

Nếu trước đó binder có `LocalValidatorFactoryBean`, ví dụ dùng `setValidator(usernameValidator)` sẽ làm mất nó khỏi **danh sách validator của binder đó**. Khi chỉ còn `UsernameRuleValidator`, các constraint Jakarta trên DTO có thể không chạy qua lượt binder validation này. Đừng suy luận rằng mọi annotation `@NotBlank` vẫn tự chạy chỉ vì dependency Hibernate Validator có mặt.

Còn:

```java
// Thay tất cả bằng danh sách được chỉ định.
binder.replaceValidators(usernameValidator, emailValidator);
```

có thể chủ động hữu ích trong trường hợp đặc biệt, nhưng thường không phải lựa chọn nếu chỉ muốn **bổ sung** quy tắc.

Khi thêm validator, `DataBinder` kiểm tra `supports(target.getClass())` khi có target phù hợp. Nếu validator không hỗ trợ class đang được bind, việc cấu hình có thể thất bại bằng `IllegalStateException`. Đừng dùng một `@InitBinder` rộng để thêm validator chuyên cho `SignupForm` lên binder của mọi DTO.

### Một lượt validate chạy nhiều validator ra sao?

Với danh sách chứa:

```text
[ MVC global LocalValidatorFactoryBean,
  UsernameRuleValidator,
  EmailDomainRuleValidator ]
```

khi binder chạy validation:

1. Global validator đánh giá các constraint Jakarta trên `SignupForm`.
2. Username validator kiểm tra rule đặt trước cho `username`.
3. Email domain validator kiểm tra rule riêng cho `email`.
4. Lỗi của cả ba được ghi vào cùng `BindingResult` của form.

Đó là **mô hình logic**; đừng thiết kế nghiệp vụ phụ thuộc vào thứ tự cụ thể của các lỗi trả về. Các validator có thể phát hiện nhiều lỗi cùng một field, và kết quả kiểm thử nên có sắp xếp chuẩn hóa khi thứ tự không phải hợp đồng.

Mặc định việc ghi lỗi ở một validator **không đồng nghĩa tất cả validator khác tự dừng**. Nếu muốn bỏ qua kiểm tra nghiệp vụ tốn kém khi có binding errors, hãy thiết kế validator/bước kiểm tra tương ứng và kiểm thử quy tắc đó thay vì trông chờ danh sách tự short-circuit.

## 6. Ví dụ hoàn chỉnh Java 17 + Spring Boot 3.5.6: ba bộ kiểm tra cùng chạy

Ví dụ dưới đây tạo một HTTP endpoint nhận form. Nó sử dụng:

- **Global:** Jakarta constraints trên DTO, được thực thi qua validator MVC mặc định.
- **Local 1:** Spring Validator không cho phép username là `admin`.
- **Local 2:** Spring Validator không cho email thuộc domain `blocked.test`.
- **Composition:** `@InitBinder("signup")` gọi `addValidators(v1, v2)`, không đụng vào validator toàn cục.

Không cần database hoặc template engine. Mục tiêu là thấy rõ nhiều lỗi từ nhiều nguồn được tích lũy trong cùng `BindingResult`.

### 6.1. Cấu trúc dự án

```text
mvc-multi-validator/
├── pom.xml
└── src/main/java/demo/mvc/
    ├── MultiValidatorApplication.java
    ├── SignupForm.java
    ├── UsernameRuleValidator.java
    ├── EmailDomainRuleValidator.java
    └── SignupController.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>mvc-multi-validator</artifactId>
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

`spring-boot-starter-web` thiết lập Spring MVC/embedded server. `spring-boot-starter-validation` bổ sung Jakarta Validation provider để annotation trên DTO được xử lý. Dự án dùng Java 17 và Maven 3.x.

### 6.3. MultiValidatorApplication.java

```java
package demo.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiValidatorApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiValidatorApplication.class, args);
    }
}
```

### 6.4. SignupForm.java

```java
package demo.mvc;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank
    private String username;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    public SignupForm() {
    }

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

Các constraint thuộc nhóm `Default`: `username` và `email` phải có nội dung, `email` phải đúng cú pháp, `age` phải khác `null` và từ 18 trở lên.

### 6.5. UsernameRuleValidator.java

```java
package demo.mvc;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class UsernameRuleValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        if ("admin".equalsIgnoreCase(form.getUsername())) {
            errors.rejectValue(
                "username", "reservedUsername",
                "Tên đăng nhập được dành riêng");
        }
    }
}
```

Validator này không gọi database hoặc thay đổi object. Dùng `"admin".equalsIgnoreCase(...)` an toàn khi username là `null`.

### 6.6. EmailDomainRuleValidator.java

```java
package demo.mvc;

import java.util.Locale;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class EmailDomainRuleValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        String email = form.getEmail();

        if (email != null && email.toLowerCase(Locale.ROOT)
                .endsWith("@blocked.test")) {
            errors.rejectValue(
                "email", "blockedDomain",
                "Không nhận địa chỉ từ miền này");
        }
    }
}
```

Rule dùng `endsWith("@blocked.test")` nhằm kiểm tra phần cuối chính xác. Đây là **chính sách minh họa**, không phải bộ phân tích email tổng quát; cú pháp email vẫn do `@Email` của Bean Validation xử lý. Trong hệ thống thật, các quy tắc về domain cần được thiết kế/thử nghiệm với IDN, normalization và hợp đồng email riêng của ứng dụng.

### 6.7. SignupController.java

```java
package demo.mvc;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.stream.Collectors;

@RestController
public class SignupController {

    private final UsernameRuleValidator usernameRule;
    private final EmailDomainRuleValidator emailDomainRule;

    public SignupController(
            UsernameRuleValidator usernameRule,
            EmailDomainRuleValidator emailDomainRule) {
        this.usernameRule = usernameRule;
        this.emailDomainRule = emailDomainRule;
    }

    @InitBinder("signup")
    void configureSignupBinder(WebDataBinder binder) {
        // Giữ Bean Validation toàn cục, bổ sung hai rule cục bộ.
        binder.addValidators(usernameRule, emailDomainRule);
    }

    @PostMapping(
        path = "/signup",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> signup(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            String details = errors.getFieldErrors().stream()
                .map(error -> error.getField() + ":" + simpleCode(error))
                .sorted()
                .collect(Collectors.joining(","));

            return ResponseEntity.badRequest()
                .body("INVALID|" + details);
        }

        return ResponseEntity.ok("ACCEPT|" + form.getUsername());
    }

    private static String simpleCode(FieldError error) {
        String[] codes = error.getCodes();
        return (codes == null || codes.length == 0)
            ? "unknown"
            : codes[codes.length - 1];
    }
}
```

Điểm cần nhìn kỹ:

1. Cả hai class Spring `Validator` có `@Component` và được inject qua constructor, không khởi tạo lại mỗi request.
2. `@InitBinder("signup")` tác động lên binder của model attribute `signup`; nó **thêm** hai validator vào danh sách sẵn có.
3. `@Valid` khiến MVC thực hiện validation trên `SignupForm` đã bind. Global Bean Validation xử lý các annotation Jakarta, còn hai validator local bổ sung lỗi theo nghiệp vụ.
4. `BindingResult errors` đứng ngay sau `SignupForm form`, cho phép controller đọc nhiều lỗi của cùng form.
5. Các lỗi được chuyển thành `field:code` và `sorted()`, tránh phụ thuộc thứ tự framework tạo `FieldError`.
6. `ResponseEntity.badRequest()` là lựa chọn **do chính controller thực hiện**, không phải vì `BindingResult` tự sinh HTTP 400.

**Quan trọng:** Không khai báo thêm một `WebMvcConfigurer#getValidator()` tùy biến trong ứng dụng mẫu. Mục tiêu là chứng minh việc thêm local validators **vẫn giữ cơ chế global mặc định**.

### 6.8. Chạy ứng dụng

Từ thư mục chứa `pom.xml`:

```bash
mvn -q spring-boot:run
```

Với cấu hình mặc định và cổng còn trống, web server lắng nghe tại `http://localhost:8080`. Gửi các yêu cầu sau từ terminal bash, zsh hoặc WSL khác.

**Trường hợp A — mọi điều kiện đều hợp lệ:**

```bash
curl -s -X POST 'http://localhost:8080/signup' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=alice' \
  --data-urlencode 'email=alice@example.org' \
  --data-urlencode 'age=22'
```

HTTP 200 OK, body:

```text
ACCEPT|alice
```

**Trường hợp B — lỗi global Jakarta và local username validator:**

```bash
curl -s -X POST 'http://localhost:8080/signup' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin' \
  --data-urlencode 'email=broken' \
  --data-urlencode 'age=17'
```

HTTP 400 Bad Request, body:

```text
INVALID|age:Min,email:Email,username:reservedUsername
```

Ba lỗi chứng minh sự kết hợp:

- `age:Min` đến từ `@Min(18)` toàn cục.
- `email:Email` đến từ `@Email` toàn cục.
- `username:reservedUsername` đến từ `UsernameRuleValidator` cục bộ.

**Trường hợp C — lỗi local email validator:**

```bash
curl -s -X POST 'http://localhost:8080/signup' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=alice' \
  --data-urlencode 'email=alice@blocked.test' \
  --data-urlencode 'age=22'
```

HTTP 400 Bad Request, body:

```text
INVALID|email:blockedDomain
```

Địa chỉ có cấu trúc email thông thường, nhưng vi phạm chính sách `EmailDomainRuleValidator`.

**Trường hợp D — cả ba bộ kiểm tra phát hiện lỗi trong một request:**

```bash
curl -s -X POST 'http://localhost:8080/signup' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin' \
  --data-urlencode 'email=alice@blocked.test' \
  --data-urlencode 'age=17'
```

HTTP 400 Bad Request, body:

```text
INVALID|age:Min,email:blockedDomain,username:reservedUsername
```

Đây là tình huống trung tâm của bài: **global constraint + hai local validators cùng đóng góp FieldError vào một BindingResult**.

Lưu ý: Các khối output thể hiện **HTTP response body do ứng dụng trả**, không phải toàn bộ stdout của Spring Boot hay Maven. `curl -s` in body và không tự thêm dòng mới. Log/headers có thể khác tùy môi trường. Mã lỗi được lấy từ `FieldError#getCodes()` ở mức tổng quát cuối cùng, vì tên mã ở mức cụ thể hơn phụ thuộc `MessageCodesResolver`.

### 6.9. Khi cố tình thay addValidators bằng setValidator

Nếu sửa `configureSignupBinder` thành:

```java
@InitBinder("signup")
void configureSignupBinder(WebDataBinder binder) {
    binder.setValidator(usernameRule);
}
```

thì danh sách validator đã được binder cấu hình trước đó bị thay bằng **chỉ usernameRule**. `EmailDomainRuleValidator` không còn được thêm, và validator MVC toàn cục trước đó cũng bị bỏ khỏi danh sách này. Trong mẫu hiện tại, điều đó có thể khiến `@Min` hoặc `@Email` trên DTO **không còn tạo lỗi qua lượt binder validation** dù annotation vẫn hiện diện.

Đây là đoạn **thay thế để phân tích tác dụng API**, không chạy đồng thời với source chính ở mục 6. Để tránh tạo lỗ hổng kiểm tra đầu vào, ưu tiên `addValidators` khi muốn giữ quy tắc mặc định.

## 7. Phạm vi cục bộ và phạm vi toàn cục qua ControllerAdvice

### 7.1. @InitBinder trong một controller

Trong `SignupController`, `@InitBinder("signup")` chỉ được áp dụng tại controller và binder có object name `signup`. Đổi tên attribute thành `"registration"` mà không cập nhật `@InitBinder` sẽ làm thay đổi việc rule local được gắn hay không.

`@InitBinder` không biến validator thành interceptor toàn hệ thống. Nó chỉ điều chỉnh những `WebDataBinder` tương ứng trong vòng đời xử lý controller request.

### 7.2. @InitBinder trong @ControllerAdvice

Để nhiều controller có cùng chính sách, có thể đặt phương thức binder ở `@ControllerAdvice`:

```java
// Minh họa riêng, KHÔNG thêm cùng lúc vào chương trình mục 6.
@ControllerAdvice(assignableTypes = {
    SignupController.class,
    PartnerSignupController.class
})
public class SignupBinderAdvice {

    private final UsernameRuleValidator usernameRule;

    public SignupBinderAdvice(UsernameRuleValidator usernameRule) {
        this.usernameRule = usernameRule;
    }

    @InitBinder("signup")
    void configure(WebDataBinder binder) {
        binder.addValidators(usernameRule);
    }
}
```

Đây là **đoạn tích hợp** đòi hỏi `PartnerSignupController` và các import/bean đã có. Với `@ControllerAdvice`, Spring có thể áp dụng phương thức `@InitBinder` cho các controller thuộc phạm vi selector; `@InitBinder("signup")` giới hạn theo tên model attribute. Nếu bạn **vừa giữ bản local vừa thêm advice ở trên**, cùng validator có thể được thêm hai lần và tạo lỗi trùng. Khi chuyển một chính sách từ controller sang advice, hãy quản lý một nguồn đăng ký rõ ràng.

### 7.3. Toàn cục MVC khác toàn cục của ứng dụng

Chỉ định global validator qua `WebMvcConfigurer#getValidator()` ảnh hưởng tới hạ tầng MVC. Nhưng service gọi trực tiếp ở Java, scheduled method, repository hay event listener **không tự động** đi qua request binder. Nếu cần kiểm tra ở service boundary, cân nhắc Bean Validation chủ động, Spring `@Validated` + method validation phù hợp hoặc một tầng bảo đảm invariant riêng.

Validator của request DTO cũng không thay thế việc enforce uniqueness trong database, giao dịch hay authorization server-side.

## 8. Các nguyên tắc khi nhiều validator cùng chạy

### 8.1. supports() phải chính xác

Một validator chuyên kiểm tra `SignupForm` không nên trả `true` cho mọi class. Ví dụ:

```java
@Override
public boolean supports(Class<?> type) {
    return SignupForm.class.isAssignableFrom(type);
}
```

Cách này cho phép `SignupForm` và subclass của nó. Dùng `type == SignupForm.class` nếu bạn thực sự chỉ muốn class đó, không hỗ trợ subtype. Khi binder kiểm tra validator có phù hợp target hay không, `supports()` sai có thể làm cấu hình thất bại hoặc dẫn tới `ClassCastException` trong `validate()`.

### 8.2. Đừng dựa vào thứ tự lỗi

Các validator có thể thêm nhiều `FieldError` cho cùng property. Ví dụ một email rỗng có thể vi phạm `@NotBlank`; với một giá trị email có cú pháp sai và domain bị chặn, cả rule Jakarta và rule custom có thể phát hiện lỗi tùy chính sách.

Khi API client cần thứ tự cố định, hãy sắp xếp theo field và code, hoặc thiết kế một cấu trúc lỗi rõ ràng. Đừng viết business logic dựa trên `getFieldErrors().get(0)` là lỗi nghiêm trọng nhất nếu thứ tự không được quy định.

### 8.3. Validation hints và @Validated

Với:

```java
@PostMapping("/signup")
public String submit(
        @Validated(AdvancedChecks.class)
        @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {
    // ...
    return errors.hasErrors() ? "INVALID" : "OK";
}
```

đây là **đoạn minh họa** yêu cầu interface `AdvancedChecks` và imports. `LocalValidatorFactoryBean` hỗ trợ nhóm Jakarta Bean Validation qua `SmartValidator`; constraint thuộc nhóm `Default` không tự chạy chỉ vì form được kiểm tra theo nhóm khác, trừ khi nhóm đó được đưa vào hợp đồng validation.

Hai class custom ở mục 6 chỉ triển khai Spring `Validator`, không phải `SmartValidator`. Chúng không tự hiểu `AdvancedChecks` và tiếp tục thực hiện logic của mình khi được binder gọi. Nếu cần rule custom phụ thuộc group, hãy dùng API `SmartValidator`/Jakarta groups có chủ đích và kiểm thử các hint cụ thể.

### 8.4. Lỗi field và lỗi object

`errors.rejectValue("email", "blockedDomain")` tạo lỗi gắn với một field, còn `errors.reject("duplicateAccount")` tạo lỗi mức object. Sau binding, controller có thể dùng:

```java
errors.getFieldErrors();  // Lỗi theo property
errors.getGlobalErrors(); // Lỗi mức object
errors.getAllErrors();    // Cả hai loại
```

Không chỉ in `getFieldErrors()` trong ứng dụng có custom validator tạo global errors, vì điều đó sẽ làm mất một phần thông tin lỗi. Ví dụ HTTP ở mục 6 chỉ dùng `rejectValue` nên in field errors là đủ cho bài thực hành.

## 9. Phân biệt validation trên argument và method validation trong MVC

Từ Spring Framework 6.1, MVC còn có **built-in method validation** khi handler có constraint trực tiếp trên method parameter hoặc return value.

### Validation của command object

Ví dụ:

```java
@PostMapping("/signup")
public String submit(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors) {
    // ...
    return "done";
}
```

Khi không có yếu tố kích hoạt method validation cho toàn phương thức, các constraint của object được đánh giá qua argument binder. Validator toàn cục và local đã đăng ký trong binder có thể cùng ghi lỗi; controller nhận `BindingResult` liền kề.

### Direct method constraint

Ví dụ:

```java
@GetMapping("/reports")
public String report(@RequestParam("page") @Min(1) int page) {
    return "page=" + page;
}
```

`@Min(1)` ở **trên chính tham số method**, không phải một field bên trong DTO. Trong Spring MVC 6.1+, lỗi thường đi qua `HandlerMethodValidationException`. Không nên mặc định rằng `@InitBinder("signup")` hay các local Spring `Validator` cho `SignupForm` sẽ xử lý constraint này.

Khi có cả `@Valid` DTO và direct method constraint khác, cơ chế method validation có thể bao gồm cả cascade validation của DTO và dùng đường exception khác. Vì vậy, hãy kiểm thử thực tế những chữ ký có đồng thời cả hai, thay vì suy luận toàn bộ lỗi luôn vào cùng `BindingResult`.

**Lưu ý:** Với controller Spring MVC 6.1+, tài liệu khuyên bỏ `@Validated` cấp class khi muốn dùng built-in method validation; annotation cấp class có thể kích hoạt đường Spring AOP method validation, khác về proxy và loại exception.

## 10. Binding lỗi chuyển kiểu, HTTP status và xử lý tại controller

Validator không thay thế data binding. Với DTO chứa `Integer age`, nếu request gửi `age=abc`, conversion từ String sang Integer có thể thất bại trước khi constraint `@Min` đánh giá. Binder ghi `typeMismatch` trong `BindingResult` khi đường form binding cho phép.

Một số đường lỗi khác:

| Vấn đề | Nguồn phát sinh | Xử lý |
| --- | --- | --- |
| `age=abc` với `@ModelAttribute` | `WebDataBinder` chuyển kiểu | Có thể quan sát `FieldError` `typeMismatch` |
| `age=17` với `@Min(18)` | Jakarta Bean Validation | `FieldError` theo mã `Min` |
| Username `admin` | Local `UsernameRuleValidator` | `FieldError` theo mã `reservedUsername` |
| Email domain bị chặn | Local `EmailDomainRuleValidator` | `FieldError` theo mã `blockedDomain` |
| JSON body không parse được | HTTP message converter | Có thể ném `HttpMessageNotReadableException` trước validation |
| `@RequestParam @Min` trực tiếp sai | MVC built-in method validation | `HandlerMethodValidationException` |
| Service method `@Validated` qua AOP sai | MethodValidationPostProcessor/provider | Loại exception tùy cấu hình AOP |

**Có `BindingResult` không đồng nghĩa framework tự chọn HTTP 400.** Khi có result ngay sau `@ModelAttribute`, handler có thể chạy và tự chọn view/status. Trong ví dụ, controller dùng `ResponseEntity.badRequest()`, còn ứng dụng server-rendered form có thể trả lại view kèm field errors.

Nếu không khai báo `BindingResult` phù hợp trong luồng argument validation, Spring thường ném `MethodArgumentNotValidException` để hạ tầng exception handler xử lý. Khi cần chuẩn hóa JSON lỗi trên nhiều endpoint, dùng `@ControllerAdvice`/`ResponseEntityExceptionHandler` đúng exception type.

## 11. Kiểm thử đa validator

Bộ kiểm thử nên bao phủ cả **đăng ký binder** và **hành vi lỗi**:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Form hợp lệ | HTTP 200, không có FieldError |
| `age=17` | Lỗi `Min` từ global Bean Validation |
| `username=admin` | Lỗi `reservedUsername` từ local validator |
| Email thuộc `blocked.test` | Lỗi `blockedDomain` từ local validator |
| Cả ba quy tắc sai | Một `BindingResult` chứa các lỗi từ nhiều nguồn |
| `age=abc` | Có lỗi binding/type conversion, không dispatch nghiệp vụ |
| Controller khác không có `@InitBinder` tương ứng | Không bị áp chính sách local của controller hiện tại |
| Một DTO khác bị add validator không hỗ trợ | Không dùng cách đăng ký rộng gây lỗi `supports` |
| Thay `addValidators` bằng `setValidator` | Phát hiện mất các constraint được global validator xử lý trong lượt binder |
| Có global error qua `reject` | Test `getGlobalErrors()` bên cạnh `getFieldErrors()` |
| Dùng `@Validated(SomeGroup.class)` | Bean Validation và custom validators có group behavior đúng như thiết kế |
| Method direct constraint trên handler | Phân biệt đường `HandlerMethodValidationException` |

Để kiểm tra Spring MVC thật, nên dùng HTTP integration test hoặc `MockMvc` thay vì chỉ gọi:

```java
new SignupController(...).signup(form, errors);
```

Lời gọi Java trực tiếp **không khởi tạo WebDataBinder, không chạy `@InitBinder` và không gọi global validator**. Unit test các validator vẫn hữu ích để xác nhận riêng từng quy tắc, nhưng không thay thế kiểm thử cách chúng được phối hợp bởi Spring MVC.

## 12. Thiết kế validator an toàn và dễ bảo trì

1. **Tránh state thay đổi theo request trong singleton validator.** Các validator được inject như bean có thể xử lý nhiều request song song; nên dùng state bất biến hoặc state cục bộ trong `validate()`.
2. **Không sửa dữ liệu trong bước validation.** Normalize/convert là trách nhiệm của binding, formatter, service hoặc tầng xử lý được thiết kế rõ. Validator nên kiểm tra và ghi lỗi, không tự thay đổi `SignupForm`.
3. **Giữ lỗi theo mã ổn định.** Với `rejectValue("username","reservedUsername",...)`, Spring sinh các message codes có mức cụ thể/tổng quát. Dùng `MessageSource` để hỗ trợ localization thay vì chỉ hardcode thông báo tiếng Việt trong code.
4. **Giới hạn binding bằng DTO và allowed fields.** Không bind trực tiếp mọi field của JPA entity vào client request. Khi cần property binding, cân nhắc `WebDataBinder#setAllowedFields(...)` để tránh mass assignment.
5. **Không dùng validator làm cơ chế phân quyền.** Dù form được validate, caller vẫn phải được kiểm tra quyền tạo/sửa tài nguyên. Rule danh sách cấm và uniqueness quan trọng cần enforce tại tầng thích hợp, có thể gồm ràng buộc database.
6. **Không làm query tốn kém tùy tiện trong validator.** Nếu phải kiểm tra tồn tại, chú ý transaction, race condition và timeout. Với uniqueness, một lượt đọc kiểm tra trước không thay thế unique constraint ở database.
7. **Không để một field nhận lỗi trùng vô ích.** Nếu cần phối hợp nhiều rule, hãy định nghĩa thứ tự nghiệp vụ hoặc khả năng tránh kiểm tra tốn kém khi dữ liệu nền tảng đã sai; đừng lặng lẽ xóa lỗi của validator khác.
8. **Không thay global validator thiếu chủ đích.** `setValidator`/`getValidator()` có thể làm mất Bean Validation annotations trong một hoặc nhiều đường MVC. Ưu tiên thêm local validators nếu yêu cầu chỉ giới hạn một form.

## 13. Ghi nhớ và tài liệu tham khảo

**Validator toàn cục** là nền tảng kiểm tra các ràng buộc chung của Spring MVC, thường được cung cấp bởi `LocalValidatorFactoryBean`. **Validator cục bộ** áp dụng quy tắc theo controller/model attribute qua `@InitBinder`. **Nhiều validator** có thể cùng ghi lỗi vào `BindingResult` khi dùng `binder.addValidators(...)`.

Sự khác nhau quan trọng nhất là **thêm** so với **thay thế**: `addValidators` giữ danh sách đang có; `setValidator` và `replaceValidators` thay danh sách. Khi kết hợp Spring Validator với Jakarta Bean Validation, hãy giữ validator toàn cục nếu cần `@NotBlank`, `@Min`, `@Email`, đồng thời kiểm thử qua request thật để xác nhận cả các rule local hoạt động.

Tài liệu chính thức:

- Spring Framework 6.2 — *Validation* (MVC global/local validators): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html
- Spring Framework 6.2 — `@InitBinder`, phạm vi controller và advice: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — *Validation* của controller, direct method constraints: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — `DataBinder` Javadoc (`addValidators`, `setValidator`): https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 — `WebDataBinder` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/bind/WebDataBinder.html
- Spring Framework 6.2 — `LocalValidatorFactoryBean` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html
- Spring Framework 6.2 — `Validator` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/Validator.html
- Jakarta Bean Validation 3.0 specification: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
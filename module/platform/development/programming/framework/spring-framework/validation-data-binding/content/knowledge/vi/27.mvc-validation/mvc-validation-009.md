# Kết hợp Errors hoặc BindingResult với các kiểu kiểm tra trong Spring MVC

## 1. Mục tiêu: một nơi tổng hợp lỗi từ nhiều giai đoạn

Trong Spring MVC, request có thể không hợp lệ vì nhiều nguyên nhân: không chuyển được chuỗi sang số, giá trị vi phạm annotation Jakarta Validation, quy tắc kiểm tra tùy chỉnh của Spring, hoặc một chính sách nghiệp vụ chỉ biết sau khi đọc dữ liệu. Khi controller nhận một **command/form object** qua `@ModelAttribute`, các lỗi tương ứng thường có thể được ghi vào cùng một `Errors`/`BindingResult`.

Hai interface thuộc `org.springframework.validation`:

- **`Errors`**: giao diện đọc và ghi lỗi của một object; cung cấp `hasErrors()`, `getFieldErrors()`, `getGlobalErrors()`, `rejectValue(...)` và `reject(...)`.
- **`BindingResult`**: **kế thừa `Errors`** và bổ sung khả năng truy vấn kết quả data binding, chẳng hạn `getTarget()`, `getRawFieldValue(...)`, `getSuppressedFields()`, `getModel()`.

Nếu chỉ cần kiểm tra lỗi hoặc thêm lỗi, khai báo `Errors` thường đủ. Nếu cần phân biệt lỗi chuyển kiểu, xem field được bỏ qua, hoặc chuẩn bị model cho HTML form, `BindingResult` hữu ích hơn.

**Nguyên tắc số 1:** đối số `Errors` hay `BindingResult` trong chữ ký controller phải đặt **ngay sau đối số được bind/validate mà nó mô tả**. Không đặt lẫn một đối số controller khác vào giữa.

```java
@PostMapping("/signups")
public String submit(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "signup-form";
    }
    return "redirect:/success";
}
```

Đây là **fragment** của controller MVC có view, không phải chương trình Java độc lập. Những phần bên dưới giải thích cơ chế, các loại lỗi, ví dụ REST form có thể chạy và các khác biệt quan trọng với JSON/Bean Validation method.

## 2. Lỗi xuất hiện ở những giai đoạn nào?

Một request `application/x-www-form-urlencoded` được xử lý qua `@ModelAttribute` thường có luồng:

```text
HTTP POST /signups
   Content-Type: application/x-www-form-urlencoded
                   |
                   v
          Tạo/tìm command object
                   |
                   v
          Data binding từ parameters
                   |
                   +--> conversion error
                   |       ví dụ age=abc -> Integer
                   |       ghi FieldError vào BindingResult
                   |
                   v
          @Valid / @Validated
                   |
                   +--> Jakarta Bean Validation
                   |       ví dụ @NotBlank, @Min, @Email
                   |
                   +--> Spring Validator đăng ký bằng @InitBinder
                   |       ví dụ từ chối username được đặt trước
                   |
                   v
          Controller nhận object và BindingResult
                   |
                   +--> errors.hasErrors() ?
                   |       |
                   |       +--> có: hiển thị form/HTTP 400
                   |
                   +--> thêm kiểm tra nghiệp vụ (nếu dữ liệu đủ hợp lệ)
                   |       |
                   |       +--> rejectValue / reject
                   |
                   v
          Xử lý nghiệp vụ nếu không còn lỗi
```

Không phải mọi request đi qua pipeline giống nhau. Với `@RequestBody` JSON, HTTP message converter tạo object trước; nếu body sai cú pháp hoặc không deserializable, Spring có thể ném `HttpMessageNotReadableException` **trước khi có object/BindingResult hữu ích cho controller**. Với controller method có **direct parameter constraints**, Spring MVC 6.1+ có thêm nhánh method validation riêng.

### Bốn nhóm kiểm tra quan trọng

| Nhóm | Cách tạo lỗi | Vị trí điển hình | Có thể xem bằng `Errors` / `BindingResult`? |
| --- | --- | --- | --- |
| Data binding / type conversion | Không thể đổi `"abc"` thành `Integer` | `@ModelAttribute` với request parameters | **Có**, thành `FieldError`, thường `isBindingFailure() == true` |
| Jakarta Bean Validation | `@NotBlank`, `@Min`, `@Email`, custom `@Constraint` | Object sau binding với `@Valid`/`@Validated` | **Có**, Spring chuyển constraint violation thành `FieldError`/`ObjectError` |
| Spring `Validator` tùy chỉnh | `supports(...)` + `validate(Object, Errors)` | `@InitBinder`, MVC config hoặc gọi trực tiếp | **Có**, validator dùng `rejectValue` và `reject` |
| Quy tắc nghiệp vụ | Check database, trùng username, chính sách liên trường | Controller/service ở điểm thích hợp | **Có thể**, nếu chủ động gọi `result.rejectValue(...)` / `reject(...)` trước khi trả response |

Điểm phân biệt: `BindingResult` là **nơi ghi nhận lỗi**, không phải một validation engine tự động. Nó không tự xét `@Min` nếu không có `Validator` và cơ chế gọi validation.

## 3. So sánh Errors và BindingResult

Cả hai nằm trong package Spring Validation, **không phải** `jakarta.validation.Validator` hay `ConstraintViolation` của Jakarta Validation.

| Phương thức | `Errors` | `BindingResult` | Dùng khi nào |
| --- | --- | --- | --- |
| `hasErrors()`, `getErrorCount()` | Có | Có | Quyết định chặn xử lý nếu có lỗi |
| `hasFieldErrors("age")` | Có | Có | Kiểm tra lỗi một thuộc tính |
| `getFieldErrors()`, `getGlobalErrors()` | Có | Có | Tách lỗi field và lỗi object |
| `rejectValue("field", "code", "message")` | Có | Có | Thêm lỗi thuộc tính |
| `reject("code", "message")` | Có | Có | Thêm lỗi cấp object/liên trường |
| `getFieldValue("age")` | Có | Có | Hiển thị giá trị người dùng đã nhập, kể cả giá trị bị reject |
| `getTarget()` | Không | Có | Truy cập object đích của binding |
| `getRawFieldValue("age")` | Không | Có | Truy vấn raw value theo property trên target |
| `getSuppressedFields()` | Không | Có | Phát hiện property bị bỏ qua vì không được phép bind |
| `getModel()` | Không | Có | Tạo map chứa target và BindingResult cho view |

`BindingResult extends Errors`, nên một tham số `BindingResult` dùng được tại mọi nơi API chỉ yêu cầu `Errors`. Khi cần `getSuppressedFields()`, không thể gọi trực tiếp từ biến khai báo kiểu `Errors` mà không có đối tượng `BindingResult` thực tế.

### FieldError so với ObjectError

- `FieldError` liên kết lỗi với một **đường dẫn property**, ví dụ `username`, `age`, `address.zipCode`; có `getField()`, `getRejectedValue()`, `isBindingFailure()`.
- `ObjectError` thể hiện lỗi **toàn object hoặc liên trường**, không thể gán một field đơn lẻ. Ví dụ một voucher đã bị khóa hoặc cặp dữ liệu không được phép tồn tại cùng nhau.
- `FieldError` là một loại `ObjectError`, nhưng cách hiển thị thường phân biệt “bên cạnh ô input” và “thông báo chung phía đầu form”.
- Có thể có **nhiều lỗi trên cùng field**. Không mặc định mỗi property chỉ có một `FieldError`.
- Một lỗi chuyển kiểu có thể kéo theo validation error khác tùy cách binder/validator xử lý property còn `null`; khi test nên so loại và tên lỗi, không dựa vào số lỗi khi yêu cầu không đòi hỏi chính xác.

## 4. Cách khai báo tham số controller đúng và sai

### Đúng: BindingResult nằm ngay sau model

```java
@PostMapping("/profiles")
public String save(
        @Valid @ModelAttribute("profile") ProfileForm profile,
        BindingResult bindingResult,
        Model model) {
    if (bindingResult.hasErrors()) {
        return "profile-form";
    }
    return "redirect:/profiles";
}
```

### Đúng: dùng Errors nếu chỉ cần API chung

```java
@PostMapping("/profiles")
public String save(
        @Validated @ModelAttribute("profile") ProfileForm profile,
        Errors errors) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "redirect:/profiles";
}
```

### Sai: một tham số khác xen giữa

```java
@PostMapping("/profiles")
public String save(
        @Valid @ModelAttribute("profile") ProfileForm profile,
        Model model,
        BindingResult result) {
    // BindingResult không đứng ngay sau profile.
    return "profile-form";
}
```

Ba code block trên là **các chữ ký minh họa riêng**, không chép cùng lúc vào một controller. Với vị trí sai, Spring MVC không thể ghép `BindingResult` vào đối số `profile` một cách đúng quy ước; quá trình giải quyết arguments có thể ném exception thay vì đi vào method.

### Hai model objects cần hai kết quả riêng

```java
@PostMapping("/combined")
public String save(
        @Valid @ModelAttribute("person") PersonForm person,
        BindingResult personResult,
        @Valid @ModelAttribute("address") AddressForm address,
        BindingResult addressResult) {
    if (personResult.hasErrors() || addressResult.hasErrors()) {
        return "combined-form";
    }
    return "redirect:/done";
}
```

Đây là fragment để biểu diễn thứ tự, các class form được định nghĩa riêng trong ứng dụng. Không dùng một `BindingResult` duy nhất cho nhiều command objects.

**Lưu ý:** khi không có `Errors`/`BindingResult` ngay sau đối số được validate, Spring có thể phát exception mặc định (thường `MethodArgumentNotValidException`), và controller không tự nhận danh sách lỗi để trả view. Đặt tham số đúng giúp xử lý lỗi **nội bộ trong handler**, không có nghĩa mọi lỗi request trên đời đều bị giữ lại.

## 5. Kết hợp các nguồn lỗi: ví dụ chạy được bằng Spring Boot 3 và Java 17

Ví dụ sử dụng một endpoint form `POST /signups`. Ta cố ý kết hợp bốn nhóm:

1. **Binding error:** `age=abc` không đổi được thành `Integer`.
2. **Jakarta Validation:** `@NotBlank`, `@NotNull`, `@Min(18)` và `@Email`.
3. **Spring `Validator`:** không cho username `admin` và từ chối mã mời `BLOCK`.
4. **Business check:** minh họa tên `taken` đã tồn tại; chỉ chạy sau khi các lỗi binding/validation cơ bản không còn.

Để quan sát kết quả trong test, endpoint phản hồi JSON chứa **tên field lỗi** (không gửi raw rejected value), danh sách **field thất bại chuyển kiểu**, và thông điệp **global errors**. Một ứng dụng MVC thuần HTML có thể giữ nguyên cơ chế `BindingResult` nhưng trả lại template thay vì JSON.

### 5.1. Cấu trúc file

```text
mvc-errors-combination/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── ValidationTypesApplication.java
    │   ├── SignupForm.java
    │   ├── SignupPolicyValidator.java
    │   └── SignupController.java
    └── test/java/demo/
        └── SignupControllerTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-errors-combination</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

`spring-boot-starter-validation` cung cấp Jakarta Validation provider cho `@Valid` trên controller argument. Nếu chỉ thêm annotation vào code mà không có provider/validator được cấu hình, không nên mong Bean Validation chạy như ví dụ.

### 5.3. ValidationTypesApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationTypesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationTypesApplication.class, args);
    }
}
```

### 5.4. SignupForm.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {
    @NotBlank
    private String username;

    @NotNull
    @Min(18)
    private Integer age;

    @NotBlank
    @Email
    private String email;

    private String invitation;

    public String getUsername() {
        return username;
    }
    public void setUsername(String username) {
        this.username = username;
    }

    public Integer getAge() {
        return age;
    }
    public void setAge(Integer age) {
        this.age = age;
    }

    public String getEmail() {
        return email;
    }
    public void setEmail(String email) {
        this.email = email;
    }

    public String getInvitation() {
        return invitation;
    }
    public void setInvitation(String invitation) {
        this.invitation = invitation;
    }
}
```

Model này có constructor no-args do Java cung cấp và các public setters phù hợp với property binding. Dùng `Integer` để phân biệt giá trị không nhập (`null`, bị `@NotNull` từ chối) với giá trị số nhỏ hơn 18 (bị `@Min` từ chối). `@Min` không phải bộ parse số: `age=abc` là lỗi chuyển kiểu trước giai đoạn đánh giá tuổi.

### 5.5. SignupPolicyValidator.java

```java
package demo;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class SignupPolicyValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;

        if ("admin".equalsIgnoreCase(form.getUsername())) {
            errors.rejectValue(
                    "username",
                    "username.reserved",
                    "Username is reserved");
        }

        if ("BLOCK".equalsIgnoreCase(form.getInvitation())) {
            errors.reject(
                    "invitation.blocked",
                    "Invitation is blocked");
        }
    }
}
```

`supports(...)` cho biết validator làm việc với kiểu nào. `validate(...)` ghi lỗi lên đối tượng `Errors` do MVC cung cấp:

- `rejectValue(...)` tạo lỗi **field** của `username`.
- `reject(...)` tạo lỗi **global/object** của command object.

Tại đây validator **không tự truy cập database** và không ném exception nếu dữ liệu không hợp lệ; nó ghi lỗi để controller tổng hợp. Tên mã `username.reserved` và `invitation.blocked` là **error code ứng dụng tự định nghĩa**, không phải constraint annotation Jakarta.

### 5.6. SignupController.java

```java
package demo;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;
import java.util.Objects;

@RestController
public class SignupController {

    @InitBinder("signup")
    public void initSignupBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "username", "age", "email", "invitation");
        binder.addValidators(new SignupPolicyValidator());
    }

    @PostMapping(
        path = "/signups",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> signup(
            @Valid @ModelAttribute("signup") SignupForm form,
            BindingResult result) {

        // Việc bind, chuyển kiểu và @Valid đã xảy ra trước dòng này.
        // Chỉ kiểm tra business rule nếu form đủ hợp lệ để đánh giá.
        if (!result.hasErrors()
                && "taken".equalsIgnoreCase(form.getUsername())) {
            result.rejectValue(
                    "username",
                    "username.taken",
                    "Username is already used");
        }

        if (result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest().body(Map.of(
                    "ok", false,
                    "code", "DISALLOWED_FIELDS"
            ));
        }

        if (result.hasErrors()) {
            List<String> fields = result.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            List<String> bindingFields = result.getFieldErrors().stream()
                    .filter(FieldError::isBindingFailure)
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            List<String> globalMessages = result.getGlobalErrors().stream()
                    .map(ObjectError::getDefaultMessage)
                    .map(m -> Objects.toString(m, "Invalid object"))
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "ok", false,
                    "code", "INVALID_SIGNUP",
                    "fields", fields,
                    "bindingFields", bindingFields,
                    "globalMessages", globalMessages
            ));
        }

        return ResponseEntity.ok(Map.of(
                "ok", true,
                "username", form.getUsername()
        ));
    }
}
```

**Điểm cần quan sát:**

- `@Valid` kích hoạt Jakarta Bean Validation đối với `SignupForm`. Spring MVC kết hợp với `SignupPolicyValidator` đã được thêm bằng `@InitBinder("signup")`; validator tùy chỉnh không thay thế global Bean Validator vì ở đây dùng `addValidators(...)`, không dùng `setValidator(...)`.
- `BindingResult` đứng **ngay sau** `@ModelAttribute` nên controller có thể xử lý lỗi trong chính method thay vì luôn để MVC ném exception mặc định.
- `getFieldErrors()` chứa các lỗi field từ nhiều nguồn. `isBindingFailure()` phân biệt lỗi type conversion khi cần. `getGlobalErrors()` chứa lỗi được tạo bằng `reject(...)`.
- `result.rejectValue(...)` trong controller là ví dụ cách thêm **business rule**. Vì nó chỉ chạy khi `!result.hasErrors()`, ta tránh tra cứu/đánh giá quy tắc nghiệp vụ khi dữ liệu đầu vào chưa hợp lệ.
- `getSuppressedFields()` giúp phát hiện client cố gửi property ngoài allowlist; bản thân việc suppress không nhất thiết tự trở thành `FieldError`. Ví dụ chủ động trả mã `DISALLOWED_FIELDS` thay vì lặng lẽ chấp nhận.
- Khi trả `fields`, ví dụ chỉ tiết lộ tên field lỗi, không đưa giá trị bị từ chối ra response; đây là lựa chọn phù hợp để giảng giải và giảm rủi ro lộ dữ liệu cá nhân.

**Lưu ý về Spring validators:** `@InitBinder` cục bộ dành cho binder tên `signup`; nếu bạn đổi tên `@ModelAttribute("signup")` nhưng không đổi `@InitBinder`, custom validator có thể không được gắn vào binder như mong đợi. Chọn `addValidators` khi muốn **kết hợp** với global Jakarta Validator; sử dụng `setValidator`/`replaceValidators` chỉ khi thực sự muốn thay đổi danh sách validators.

### 5.7. SignupControllerTest.java với MockMvc

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItems;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validFormIsAccepted() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "lan")
                        .param("age", "20")
                        .param("email", "lan@example.org"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ok").value(true))
                .andExpect(jsonPath("$.username").value("lan"));
    }

    @Test
    void jakartaConstraintsAreCollected() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "")
                        .param("age", "16")
                        .param("email", "not-an-email"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_SIGNUP"))
                .andExpect(jsonPath("$.fields",
                        hasItems("username", "age", "email")))
                .andExpect(jsonPath("$.bindingFields.length()").value(0));
    }

    @Test
    void typeMismatchIsTrackedSeparately() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "lan")
                        .param("age", "abc")
                        .param("email", "lan@example.org"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_SIGNUP"))
                .andExpect(jsonPath("$.bindingFields", hasItems("age")));
    }

    @Test
    void springValidatorCreatesFieldError() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "admin")
                        .param("age", "23")
                        .param("email", "admin@example.org"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields", hasItems("username")));
    }

    @Test
    void springValidatorCreatesGlobalError() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "lan")
                        .param("age", "23")
                        .param("email", "lan@example.org")
                        .param("invitation", "BLOCK"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.globalMessages",
                        hasItems("Invitation is blocked")));
    }

    @Test
    void controllerCanAddBusinessFieldError() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "taken")
                        .param("age", "23")
                        .param("email", "taken@example.org"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields", hasItems("username")));
    }

    @Test
    void massAssignmentAttemptIsRejected() throws Exception {
        mvc.perform(post("/signups")
                        .contentType("application/x-www-form-urlencoded")
                        .param("username", "lan")
                        .param("age", "23")
                        .param("email", "lan@example.org")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"));
    }
}
```

Chạy bằng Java 17+ và Maven trong thư mục dự án:

```bash
mvn -q test
```

**Kỳ vọng kiểm thử:** bảy test thành công (exit code 0) khi môi trường Maven tải đủ dependencies. Không áp đặt stdout Maven cụ thể vì log của Spring/Test/JUnit có thể thay đổi theo bản thư viện và cấu hình log. Những assertion kiểm tra **HTTP status, error code, tên field lỗi, loại lỗi binding và global error** thay vì phụ thuộc vào chuỗi message Bean Validation mặc định.

Chạy ứng dụng:

```bash
mvn spring-boot:run
```

Và gửi form bằng curl:

```bash
curl -i -X POST http://localhost:8080/signups \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=lan' \
  --data-urlencode 'age=20' \
  --data-urlencode 'email=lan@example.org'

curl -i -X POST http://localhost:8080/signups \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin' \
  --data-urlencode 'age=abc' \
  --data-urlencode 'email=bad'
```

Request thứ nhất trả **200 OK** với `ok=true`; request thứ hai trả **400 Bad Request** với code `INVALID_SIGNUP` và danh sách `fields`/`bindingFields`. Vì lỗi chuyển kiểu và annotation constraint có thể cùng được ghi trên field, ví dụ in **tên distinct** thay vì dựa vào số lỗi trên field.

## 6. Cách kiểm tra riêng từng loại lỗi bên trong BindingResult

### 6.1. Lỗi chuyển đổi kiểu

Khi `age` nhận `"abc"` nhưng property là `Integer`, lỗi thường có code gốc như `typeMismatch`. Spring tạo `FieldError` có `isBindingFailure() == true`. Chúng ta có thể kiểm tra:

```java
boolean invalidAgeType = result.getFieldErrors("age")
        .stream()
        .anyMatch(FieldError::isBindingFailure);
```

Đây là fragment trong controller đã có biến `BindingResult result`. Không dựa vào text message “Failed to convert…” vì message có thể được nội suy bằng `MessageSource` và locale.

### 6.2. Vi phạm Jakarta Validation

Với `@NotBlank` trên `username`, lỗi được Spring adapter chuyển thành `FieldError` và thường có `isBindingFailure() == false`. Code của constraint được đưa vào cơ chế message codes để có thể nội suy/localize. Ví dụ:

```java
boolean invalidUsername = result.hasFieldErrors("username");
boolean hasGlobal = result.hasGlobalErrors();
int totalErrors = result.getErrorCount();
```

Các phép kiểm tra này chỉ nhìn **trạng thái lỗi**, không tự xác định nguồn nào sinh lỗi. Nếu cần phân loại chắc chắn theo nghiệp vụ, hãy dùng error codes được định nghĩa thống nhất thay vì chỉ xem cờ `isBindingFailure()`.

### 6.3. Lỗi global / liên trường

Khi một quy tắc không thuộc riêng field nào, dùng:

```java
result.reject(
    "registration.invalidCombination",
    "The selected values cannot be used together"
);
```

Ví dụ này tạo `ObjectError`, lấy bằng `getGlobalErrors()`. Không ép lỗi liên trường phải gắn vào một property tùy ý chỉ để trả form: UI có thể hiển thị ở đầu form hoặc dưới nhóm trường liên quan.

### 6.4. rejectValue và reject khác nhau thế nào?

```java
result.rejectValue(
    "username",
    "username.taken",
    "Username is already used"
);

result.reject(
    "invitation.blocked",
    "Invitation is blocked"
);
```

- `rejectValue` nhận **field path**, **error code**, **default message** và có overload chứa arguments nội suy.
- `reject` nhận code và message ở **cấp object**.
- Code có thể được giải quyết bởi `MessageCodesResolver` và `MessageSource`; vì vậy `ObjectError#getCodes()` thường có nhiều key theo mức độ cụ thể, giúp thiết kế i18n.
- Nếu controller dùng nested path, field name cần đúng relative path trong ngữ cảnh; tránh gọi `rejectValue` vào property không có trên DTO.

### 6.5. Khi nào nên kiểm tra nghiệp vụ?

Một cách phòng thủ:

```java
if (result.hasErrors()) {
    return "signup-form";
}

// Dữ liệu đã qua type conversion và validation cơ bản.
if (userService.existsByUsername(form.getUsername())) {
    result.rejectValue(
        "username", "username.taken", "Username already exists");
}

if (result.hasErrors()) {
    return "signup-form";
}

// Chỉ lúc này mới ghi dữ liệu.
userService.register(form);
return "redirect:/success";
```

Đây là **fragment minh họa**, không phải code chạy độc lập: `userService` và `signup-form` là những thành phần cần có trong ứng dụng. Cách này tránh query DB khi field dữ liệu còn sai kiểu hoặc thiếu. Lưu ý kiểm tra tồn tại username trước khi insert **không đủ** để ngăn race condition; dữ liệu có yêu cầu unique vẫn cần ràng buộc database hoặc cơ chế nhất quán phù hợp.

## 7. @Valid, @Validated và nhiều validation groups

`jakarta.validation.Valid` kích hoạt Bean Validation và cascade vào object con đã đánh dấu `@Valid`. Nó **không phải** constraint buộc khác null: muốn bắt buộc field tồn tại, thêm `@NotNull` hoặc `@NotBlank` phù hợp.

`org.springframework.validation.annotation.Validated` hỗ trợ chọn validation group. Ví dụ:

```java
public interface UpdateChecks {}

public class ProfileForm {
    @NotBlank(groups = UpdateChecks.class)
    private String displayName;

    // getter/setter...
}

@PostMapping("/profile")
String update(
        @Validated(UpdateChecks.class)
        @ModelAttribute("profile") ProfileForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "profile-form";
    }
    return "redirect:/profile";
}
```

Đây là fragment; class/form/controller cần đặt ở vị trí hợp lệ và đầy đủ imports. Khi đặt constraint chỉ vào `UpdateChecks`, nó **không tự thuộc Default group**. Nếu dùng `@Valid` không chỉ định group, constraint thuộc nhóm custom có thể không được chạy. Cần xem kỹ group đang active, group conversion và khả năng Spring custom `Validator` sử dụng validation hints.

**Hai lưu ý:**

1. `BindingResult` không quyết định group; nó nhận lỗi sau khi validation engine đã chạy theo group.
2. Một Spring `Validator` thuần chỉ có `validate(Object, Errors)`; nó không biết group của Jakarta nếu không triển khai hoặc cấu hình cơ chế validation hints tương ứng.

## 8. @ModelAttribute so với @RequestBody và @RequestPart

### 8.1. @ModelAttribute: hợp với form và binding errors

Với `application/x-www-form-urlencoded`, `@ModelAttribute` phù hợp để bind nhiều request parameters vào JavaBean. Lỗi chuyển kiểu field (ví dụ số) và Bean Validation có thể cùng xuất hiện trong `BindingResult` ngay sau command object.

Nếu controller dùng HTML view, pattern phổ biến:

```java
@PostMapping("/settings")
public String save(
        @Valid @ModelAttribute("settings") SettingsForm settings,
        BindingResult result) {

    if (result.hasErrors()) {
        return "settings-form";
    }

    return "redirect:/settings";
}
```

Đây là fragment của controller sử dụng template, không phải handler trong project REST runnable phía trên. Spring MVC có thể dùng các lỗi trong model để render message bên cạnh field và giữ giá trị request bị reject, tùy template engine.

### 8.2. @RequestBody JSON: Errors có thể nhận vi phạm DTO, không cứu được lỗi parse

Spring MVC hỗ trợ `Errors` hoặc `BindingResult` **ngay sau một `@Valid @RequestBody` argument**:

```java
@PostMapping("/api/accounts")
public ResponseEntity<?> create(
        @Valid @RequestBody AccountRequest request,
        Errors errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(
                Map.of("code", "INVALID_ACCOUNT"));
    }

    return ResponseEntity.ok().build();
}
```

Đây là fragment API JSON với `AccountRequest` được định nghĩa riêng, không nằm trong project Maven demo ở trên.

**Sự khác biệt quyết định:**

- JSON hợp lệ, Jackson tạo được `AccountRequest` nhưng `@NotBlank`/`@Min` không đạt: Spring có thể đưa lỗi DTO vào `Errors` và cho controller tự xử lý.
- JSON sai cú pháp, ví dụ `{"age":,}`, hoặc không chuyển được sang kiểu Java: HTTP message converter thường ném `HttpMessageNotReadableException` **trước khi controller chạy**. Không có object để đưa vào biến `errors`.
- Header `Content-Type` không được endpoint hỗ trợ có thể gây `HttpMediaTypeNotSupportedException` (415), không phải một lỗi field trong `BindingResult`.
- Nếu không có `Errors`/`BindingResult` phù hợp ngay sau tham số và chỉ có individual DTO validation, lỗi thường đi theo `MethodArgumentNotValidException`, mặc định 400.

Không dùng `@RequestBody` để giả định toàn bộ HTML form-urlencoded được xử lý như JSON. Spring MVC có pipeline riêng cho `@ModelAttribute`/`@RequestParam`.

### 8.3. @RequestPart multipart

Với multipart, một part có thể được converter tạo object rồi Bean Validation kiểm tra; Spring MVC cũng hỗ trợ `Errors`/`BindingResult` ngay sau `@Valid @RequestPart` argument khi có ý nghĩa. Nhưng đọc part, thiếu part, multipart parser và content-type sai vẫn có thể ném exception trước khi có binding result. Cần kiểm thử đúng media type, part name và handler signature.

## 9. Method validation trong Spring MVC 6.1+: khi BindingResult không đủ

Từ Spring Framework 6.1, MVC có **built-in method validation** khi direct constraints như `@Min`/`@NotBlank` đặt trực tiếp lên tham số method (hoặc return value). Cơ chế này có thể bao gồm nested `@Valid` và sinh `HandlerMethodValidationException`. Nó khác individual validation của DTO.

Ví dụ:

```java
@PostMapping("/search")
public String search(
        @RequestParam @Min(1) int page,
        @Valid @ModelAttribute("filters") FilterForm filters,
        BindingResult filtersResult) {

    if (filtersResult.hasErrors()) {
        return "search-form";
    }
    return "search-results";
}
```

Đây là fragment; `FilterForm` và các view cần định nghĩa riêng. Nếu `page=0`, lỗi nằm ở **tham số page**, không phải object `filters`, nên `filtersResult` **không thể tự đại diện cho mọi lỗi method**.

Theo tài liệu Spring MVC:

1. Individual object validation dùng `MethodArgumentNotValidException` khi lỗi không được tiếp nhận qua đối số `Errors` liền kề.
2. Built-in method validation có thể ném `HandlerMethodValidationException` khi lỗi thuộc tham số method không có đối số `Errors` đứng ngay sau để xử lý.
3. MVC có thể **vẫn gọi controller** nếu **tất cả** lỗi method validation nằm ở các tham số có `Errors`/`BindingResult` đứng ngay sau.
4. Nếu **bất kỳ** lỗi nào thuộc một tham số khác không có `Errors` liền kề, Spring ném `HandlerMethodValidationException` thay vì đơn giản bỏ qua lỗi.
5. `@Valid` **không phải direct constraint**; riêng nó chưa đòi phương thức MVC method validation, nhưng đặt `@NotNull` trực tiếp trên tham số có thể thay đổi nhánh.
6. Controller đánh dấu `@Validated` ở **class level** có thể dùng validation dựa trên Spring AOP proxy; nếu muốn built-in method validation Spring 6.1+, tài liệu Spring khuyến nghị bỏ class-level `@Validated` khỏi controller.

Không cố ép `HandlerMethodValidationException` thành `BindingResult` của một DTO. Nó chứa các `ParameterValidationResult` nhóm theo từng tham số; có thể xử lý bằng `ResponseEntityExceptionHandler` hoặc `@ControllerAdvice` phù hợp.

### Bảng quyết định theo chữ ký controller

| Chữ ký / tình huống | Cách xử lý phổ biến |
| --- | --- |
| `@Valid @ModelAttribute Form form, BindingResult br` | Controller xử lý lỗi binding/validation bằng `br` |
| `@Valid @RequestBody Dto dto, Errors errors`; JSON đọc được | Controller xử lý validation errors bằng `errors` |
| `@Valid @RequestBody Dto dto`; JSON đọc được nhưng DTO lỗi | Thường ném `MethodArgumentNotValidException` |
| `@RequestBody` JSON không đọc được | `HttpMessageNotReadableException`, kể cả có tham số `Errors` phía sau |
| Controller có direct `@Min` trên `@RequestParam` | Có thể kích hoạt MVC method validation và `HandlerMethodValidationException` |
| Method validation lỗi ở tất cả đối số đều có `Errors` liền kề | MVC có thể gọi controller để xử lý |
| Method validation lỗi ở một đối số không có `Errors` liền kề | Ném `HandlerMethodValidationException` |
| Đánh dấu `@Validated` class-level trên controller | Có thể chuyển sang AOP method validation; cần xem cấu hình |

## 10. BindingResult, view model và thông điệp lỗi

### 10.1. Trả lại form HTML

Spring tích hợp `BindingResult` với model attribute để view engine có thể hiển thị lỗi. Với tên object `signup`, khóa lỗi chuẩn trong model thường có dạng:

```text
org.springframework.validation.BindingResult.signup
```

Cặp object + `BindingResult` giúp view truy cập cả giá trị đã nhập và lỗi field. Trong controller trả về template name, Spring MVC thường đã quản lý phần model liên quan. Nếu tự tạo model map từ `BindingResult#getModel()`, phải giữ đúng tên object và key binding result. Không nên vô tình ghi đè model attribute sau khi binding vì view có thể mất thông tin lỗi.

Ví dụ JSP/Spring form tags (fragment minh họa):

```jsp
<form:form modelAttribute="signup" method="post">
    <form:input path="username"/>
    <form:errors path="username"/>

    <form:input path="age"/>
    <form:errors path="age"/>

    <form:errors path="*" />
    <button type="submit">Submit</button>
</form:form>
```

Cần khai báo taglib và có view resolution tương ứng trong ứng dụng. Template Thymeleaf có thể dùng `th:field`, `#fields.hasErrors(...)` và `th:errors` cho mục đích tương tự. Đây là cách *trình bày lỗi*; logic kiểm tra vẫn nằm ở binder và validators.

### 10.2. Message codes và i18n

Spring's `MessageCodesResolver` thường xây nhiều mã từ mức cụ thể đến mức chung. Ví dụ `rejectValue("age", "typeMismatch")` có thể tương ứng các key message chi tiết theo object/field/type trước khi dùng fallback. Giá trị cụ thể phụ thuộc message resolver và object name, nên tránh hardcode một mã duy nhất trong test nếu không kiểm soát resolver.

Có thể cung cấp `messages.properties` và `messages_vi.properties` để thông điệp được nội suy theo locale. Ví dụ:

```properties
username.reserved=Username này không được sử dụng
username.taken=Tên đăng nhập đã tồn tại
invitation.blocked=Mã mời này đã bị khóa
```

Nếu response API cần error code ổn định, hãy tách **machine-readable code** khỏi **localized human message** thay vì bắt client phân tích text đã dịch.

### 10.3. Không hiển thị rejected values nhạy cảm

`FieldError#getRejectedValue()` có thể chứa mật khẩu, token, email, thông tin định danh. Việc dump toàn bộ `BindingResult` vào log hoặc response là rủi ro. Trong ví dụ runnable chỉ đưa ra **tên field** và thông tin dạng lỗi chuyển kiểu; không xuất raw values.

## 11. Các lỗi thường gặp

### 11.1. Đặt BindingResult sai vị trí

**Sai:** `(@Valid Form form, Model model, BindingResult br)`. **Đúng:** `(@Valid Form form, BindingResult br, Model model)`. Với nhiều form, phải có cặp result liền sau từng object.

### 11.2. Không có @Valid hoặc @Validated

Chỉ khai báo `@NotBlank` trên DTO chưa đủ để MVC tự chạy validation của DTO trong mọi chữ ký method. Thêm `@Valid`/`@Validated` tại điểm binding thích hợp và đảm bảo Jakarta Validation provider được đăng ký.

### 11.3. Nhầm lỗi conversion với lỗi constraint

`age=abc` thường tạo `typeMismatch`, không phải `@Min(18)`. Một số trường hợp còn có thêm `@NotNull` vì field không chuyển được và để `null`. Đừng assert số lỗi cố định nếu logic của ứng dụng chỉ cần nhận diện “age không hợp lệ”.

### 11.4. Dùng setValidator thay addValidators không có chủ đích

`setValidator(...)` đặt validator đơn cho binder; một cấu hình vô tình có thể thay mất global Jakarta Validator mà MVC cung cấp. Dùng `addValidators(...)` khi cần kết hợp, và test cả constraint Jakarta lẫn Spring custom.

### 11.5. supports() trả false

Spring `Validator#supports(Class<?>)` phải nhận class model tương ứng. Nếu khai báo cho sai kiểu, Spring không nên áp validator lên target ngoài phạm vi; khi gắn bằng `@InitBinder`, cần kiểm tra class đối tượng và binder name.

### 11.6. Chỉ xem getFieldErrors mà bỏ getGlobalErrors

Một `errors.reject(...)` tạo lỗi object-level, không xuất hiện như lỗi của một property cụ thể. Khi làm API error summary hoặc render form, nên xử lý cả hai nhóm.

### 11.7. Xử lý nghiệp vụ dù form đã lỗi chuyển kiểu

Nếu tuổi chưa chuyển được thành số, việc query DB hoặc tính giá dựa trên tuổi có thể thất bại hoặc làm phát sinh side effect không mong muốn. Kiểm tra `hasErrors()` trước khi thực thi business rule dựa trên dữ liệu đã parse/validate.

### 11.8. Cho rằng BindingResult bắt được JSON sai cú pháp

Nếu `@RequestBody` JSON lỗi trong converter, controller chưa nhận object; `BindingResult` liền kề không biến parse error thành `FieldError`. Phải dùng exception handling như `ResponseEntityExceptionHandler`/`@ControllerAdvice` cho `HttpMessageNotReadableException`.

### 11.9. Dựa vào BindingResult của một object để xử lý tất cả method parameters

Direct `@Min` trên `@RequestParam` có thể dùng method validation, khác đường individual DTO validation. Đọc tài liệu Spring MVC 6.1+ và xử lý `HandlerMethodValidationException` cho các tham số không có `Errors` liền kề.

### 11.10. Chỉ dựa vào allowlist mà không xem suppressed fields

`setAllowedFields(...)` ngăn binding ngoài danh sách nhưng không nhất thiết tạo lỗi validation theo nghĩa `hasErrors()`. Khi security contract yêu cầu báo request độc hại, đọc `getSuppressedFields()` và chủ động từ chối hoặc ghi log phù hợp.

## 12. Checklist triển khai

- [ ] Chọn đúng pipeline: `@ModelAttribute` cho form parameters, `@RequestBody` cho JSON, `@RequestPart` cho multipart.
- [ ] Luôn đặt `Errors`/`BindingResult` ngay sau đối số mà nó mô tả.
- [ ] Xác định khi nào `@Valid` hoặc `@Validated(group)` cần được dùng.
- [ ] Có Jakarta Validation provider khi muốn chạy constraint annotation.
- [ ] Dùng `@InitBinder` + `addValidators(...)` nếu muốn kết hợp Spring `Validator` riêng với global validator.
- [ ] Thực hiện business validation sau bước kiểm tra tính hợp lệ cơ bản.
- [ ] Phân biệt field errors, global errors, binding failures và suppressed fields.
- [ ] Giữ response schema/API error codes nhất quán; không lộ rejected values nhạy cảm.
- [ ] Xử lý converter exceptions và MVC method validation bên ngoài phạm vi local BindingResult.
- [ ] Với HTML view, đảm bảo trả lại đúng model attribute và binding result.
- [ ] Viết MockMvc test cho happy path, constraint, type mismatch, custom field error, global error, business check và mass assignment.
- [ ] Kiểm tra version Spring: built-in controller method validation có từ Spring Framework 6.1; không coi nó tương đương mọi cấu hình AOP method validation.

## 13. Kết luận

`Errors` là giao diện **nhận và báo lỗi**; `BindingResult` là biến thể gắn với **data binding** và cung cấp thêm metadata. Khi được đặt ngay sau một `@ModelAttribute` hoặc một `@Valid @RequestBody` phù hợp, chúng giúp controller tự tổng hợp và phản hồi lỗi thay vì phải dựa hoàn toàn vào exception mặc định.

Trong cùng một `BindingResult`, bạn có thể kết hợp **lỗi chuyển kiểu**, **vi phạm Jakarta Bean Validation**, **lỗi từ Spring `Validator`** và **quy tắc nghiệp vụ bổ sung**. Tuy nhiên, **JSON không đọc được, media type sai, lỗi ở method parameter khác và lỗi hạ tầng** không tự trở thành `FieldError` của form object. Sử dụng đúng từng boundary và kiểm thử từng loại lỗi là cách xây dựng MVC validation nhất quán, dễ hiểu và dễ bảo trì.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — ModelAttribute Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — MVC Validation Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — Java Bean Validation and Spring Validator](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — Errors API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/Errors.html)

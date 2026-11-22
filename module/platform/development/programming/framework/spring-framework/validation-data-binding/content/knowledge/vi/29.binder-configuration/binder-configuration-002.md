# Giới hạn @InitBinder theo tên đối tượng trong Spring Framework

## 1. Vấn đề: cùng một controller nhưng mỗi form cần quy tắc binding khác nhau

Spring MVC dùng `WebDataBinder` để chuyển request parameters thành giá trị có kiểu, gán vào command object và phối hợp với validation. Một controller có thể xử lý nhiều form: form sửa hồ sơ công khai chỉ cho phép thay đổi biệt danh, còn form hồ sơ cá nhân cho phép sửa thêm phần giới thiệu. Hai form thậm chí có thể dùng **cùng một Java class**, nhưng **không nên có cùng chính sách cập nhật**.

Nếu viết:

```java
@InitBinder
void initialize(WebDataBinder binder) {
    binder.setAllowedFields("nickname");
}
```

phương thức khởi tạo trên sẽ áp dụng cho **mọi binder phù hợp trong controller đó**, kể cả binder của form muốn cho sửa thêm `bio`. Cách chính xác hơn là gắn **tên đối tượng đích** vào annotation:

```java
@InitBinder("publicProfile")
void initPublicProfile(WebDataBinder binder) {
    binder.setAllowedFields("nickname");
}

@InitBinder("privateProfile")
void initPrivateProfile(WebDataBinder binder) {
    binder.setAllowedFields("nickname", "bio");
}
```

Các đoạn code trên là **fragment trong Spring MVC controller**, không phải chương trình chạy độc lập. Ý nghĩa quan trọng: `"publicProfile"` và `"privateProfile"` là **tên model attribute/binder target**, **không phải tên lớp Java, tên method controller, đường dẫn HTTP, hay tên bảng database**.

Đây chính là trọng tâm của bài: **giới hạn phạm vi `@InitBinder` bằng `@InitBinder("objectName")`**, so sánh với `@InitBinder` không tham số, cấu hình nhiều tên, scope của `@ControllerAdvice`, những tác động đến `allowedFields`, `Validator`, `PropertyEditor` và kiểm thử bằng Spring MVC.

Bài sử dụng Java 17, Spring Framework 6.x/Spring Boot 3.x và `jakarta.validation.*`. Các phiên bản mới hơn có thể bổ sung tính năng, nhưng nguyên tắc tên binder ở đây được mô tả trong API `org.springframework.web.bind.annotation.InitBinder`.

## 2. @InitBinder làm gì và khi nào được gọi?

`@InitBinder` đánh dấu method cấu hình `WebDataBinder` cho việc xử lý request ở annotated controller. Spring tạo hoặc chuẩn bị binder phù hợp rồi gọi các method `@InitBinder` áp dụng trước khi bind/validate dữ liệu.

Những việc thường cấu hình:

- `binder.setAllowedFields("name", "email")`: cho phép **property binding** chỉ vào các field có trong danh sách.
- `binder.setRequiredFields("email")`: yêu cầu field có mặt trong quá trình property binding, không đồng nghĩa hoàn toàn với `@NotBlank`.
- `binder.addValidators(mySpringValidator)`: bổ sung một `org.springframework.validation.Validator` riêng cho loại form.
- `binder.registerCustomEditor(...)` hoặc `binder.addCustomFormatter(...)`: bổ sung chuyển đổi/định dạng giá trị cho binder.
- `binder.setFieldMarkerPrefix("_")` / `setFieldDefaultPrefix("!")`: tùy chỉnh hành vi marker và default của HTML form.
- `binder.setAutoGrowCollectionLimit(...)` và các thiết lập DataBinder khác: giới hạn hoặc điều chỉnh hành vi binding.

Các method `@InitBinder` điển hình trả **`void`** và nhận `WebDataBinder`; có thể nhận thêm một số đối số thuộc ngữ cảnh request (ví dụ `WebRequest` hoặc `Locale`) theo danh sách Spring cho phép. Chúng **không phải** request handler, **không nhận một `@ModelAttribute` command object để bind thay controller**, và không tạo response HTTP.

### 2.1. Luồng cho @ModelAttribute

```text
POST /profiles/public
      |
      v
DispatcherServlet -> xác định controller handler
      |
      v
Tạo / lấy @ModelAttribute("publicProfile") ProfileForm
      |
      v
Tạo WebDataBinder có objectName = "publicProfile"
      |
      +--> Chọn các @InitBinder phù hợp:
      |      @InitBinder                    -> áp dụng
      |      @InitBinder("publicProfile")     -> áp dụng
      |      @InitBinder("privateProfile")    -> KHÔNG áp dụng
      |      @InitBinder({"publicProfile", "privateProfile"}) -> áp dụng
      |
      v
Binding request parameters theo allowedFields/conversion
      |
      v
@Valid / @Validated (nếu được yêu cầu)
      |
      v
Controller nhận ProfileForm + BindingResult
```

Đây là sơ đồ khái niệm cho Spring MVC; tại runtime có thêm giai đoạn constructor binding, formatter/conversion service, validation adapter và exception resolution. Mỗi binder có **đối tượng đích và objectName tương ứng**. Không hiểu một `@InitBinder` là “chạy đúng một lần trong toàn ứng dụng”; nó có thể được gọi khi Spring tạo binder trong từng request.

## 3. @InitBinder.value(): chỉ định chính xác tên nào?

`@InitBinder` có thuộc tính `String[] value()`. Theo Javadoc, các giá trị là tên của **command/form attributes và/hoặc request parameters** mà init-binder method được phép áp dụng.

Các cách khai báo tương đương:

```java
@InitBinder("publicProfile")
void one(WebDataBinder binder) { /* ... */ }

@InitBinder(value = "publicProfile")
void alsoOne(WebDataBinder binder) { /* ... */ }

@InitBinder({"publicProfile", "privateProfile"})
void two(WebDataBinder binder) { /* ... */ }

@InitBinder
void all(WebDataBinder binder) { /* ... */ }
```

Đây là **bốn fragment riêng**, không nên copy tất cả thành các method cùng chức năng rồi tự gây ghi đè cấu hình.

| Khai báo | Ý nghĩa |
| --- | --- |
| `@InitBinder` | Không chỉ định tên: áp dụng rộng cho binder thuộc phạm vi controller/advice phù hợp |
| `@InitBinder("publicProfile")` | Chỉ áp dụng khi binder có objectName đúng `publicProfile` |
| `@InitBinder({"publicProfile","privateProfile"})` | Áp dụng khi binder có **một trong hai tên** |
| `@InitBinder(value={"a","b"})` | Cú pháp tường minh tương đương khai báo mảng tên |

**So khớp tên là theo giá trị chuỗi, phân biệt hoa/thường**. `@InitBinder("publicprofile")` không tương đương `@ModelAttribute("publicProfile")`. Các chuỗi trong `value` **không phải các mẫu URL hoặc pattern tên field**; `@InitBinder("profile*")` không có ý nghĩa “mọi objectName bắt đầu bằng profile” theo cơ chế tên này.

Điểm rất dễ nhầm: Spring cho phép chỉ định **tên request parameter** bên cạnh tên command attribute trong annotation. Tuy nhiên với form object `@ModelAttribute`, cách học và kiểm thử chắc chắn nhất là **đặt tên model attribute tường minh và dùng chính tên đó trong `@InitBinder`**. Chi tiết binder cho một simple method parameter còn phụ thuộc cách Spring resolve parameter và tạo binder; đừng suy nó là quy tắc lọc toàn bộ raw HTTP parameter của request.

### 3.1. @ModelAttribute tên tường minh

```java
@PostMapping("/profiles/public")
String update(
        @ModelAttribute("publicProfile") ProfileForm form,
        BindingResult result) {
    // Binder có objectName "publicProfile".
    return "ok";
}
```

Tên `publicProfile` được khai báo tường minh, nên dễ bảo đảm khớp với `@InitBinder("publicProfile")`. **Tên biến Java** ở đây là `form`, nhưng tên binder **không phải** `form`.

### 3.2. Tên được suy ra khi bỏ @ModelAttribute("name")

```java
@PostMapping("/profiles")
String update(@ModelAttribute ProfileForm form) {
    return "ok";
}
```

Khi không chỉ định tên, Spring dùng **quy ước đặt tên model attribute theo kiểu đối số**. Với kiểu `ProfileForm`, tên thường được suy ra là `profileForm`, **không nhất thiết trùng tên biến Java `form`**. Nếu đã viết `@InitBinder("publicProfile")`, binder được đặt tên `profileForm` sẽ **không khớp**. Đừng phụ thuộc vào tên suy luận khi cấu hình binder cần khóa scope chặt chẽ.

Trong ứng dụng có hai model attributes cùng class, tên tường minh gần như bắt buộc để phân biệt mục đích của hai binder.

### 3.3. Tên model attribute không phải tên field

Với:

```java
@ModelAttribute("publicProfile") ProfileForm form
```

và property `nickname` trên `ProfileForm`:

- Tên binder: `publicProfile`.
- Tên property được bind: `nickname`.
- Form parameter thường mang tên: `nickname`.
- Scoped binder selector: `@InitBinder("publicProfile")`.
- Danh sách field có thể bind: `binder.setAllowedFields("nickname")`.

Đừng viết `@InitBinder("nickname")` chỉ vì property của form tên `nickname`. Đừng viết `setAllowedFields("publicProfile")` với ý định “chỉ cho bind model attribute publicProfile”: allowlist áp vào **property path** trên object, không phải binder objectName.

## 4. Phân biệt hai lớp phạm vi

Có hai câu hỏi hoàn toàn khác nhau:

1. **Phương thức init binder tồn tại ở controller/advice nào?** Tức phạm vi **controller**.
2. **Phương thức init binder được áp dụng cho binder objectName nào?** Tức phạm vi **model attribute/parameter name**.

| Nơi khai báo | Có selector tên? | Tác động |
| --- | --- | --- |
| `@Controller` X + `@InitBinder` | Không | Các binder phù hợp được xử lý trong controller X |
| `@Controller` X + `@InitBinder("formA")` | Có | Chỉ binder tên `formA` trong controller X |
| `@ControllerAdvice` + `@InitBinder` | Không | Các binder trong những controller mà advice được chọn |
| `@ControllerAdvice` + `@InitBinder("formA")` | Có | Chỉ binder tên `formA` trong những controller mà advice áp dụng |
| `@ControllerAdvice(assignableTypes=SomeController.class)` + `@InitBinder("formA")` | Có cả hai | Chỉ controller được chọn **và** binder tên `formA` |

**Ví dụ advice** (fragment trong một ứng dụng có `AccountController`):

```java
@ControllerAdvice(assignableTypes = AccountController.class)
public class AccountBinderAdvice {

    @InitBinder("accountForm")
    public void accountBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "contactEmail");
    }
}
```

Ở đây `@ControllerAdvice(assignableTypes=...)` chọn **các controller**, còn `@InitBinder("accountForm")` chọn **binder name** bên trong controller được áp dụng. Không dùng `@InitBinder("accountForm")` để thay thế selector `basePackages`/`assignableTypes` của `@ControllerAdvice`.

Trong Spring MVC, **global `@InitBinder` từ `@ControllerAdvice` được áp dụng trước local `@InitBinder` trong controller**. Nếu nhiều phương thức cùng sửa một thiết lập (ví dụ liên tiếp gọi `setAllowedFields`) thì kết quả có thể bị cấu hình sau ghi đè; phải thiết kế rõ nơi nào sở hữu chính sách và kiểm thử output thực tế. Đừng mặc định rằng có nhiều `setAllowedFields` sẽ tự “lấy giao” của các danh sách cho phép.

## 5. Ví dụ end-to-end Java 17: cùng kiểu ProfileForm, hai tên, hai chính sách

Chúng ta tạo Spring Boot MVC app với **hai endpoint**, cả hai đều nhận `ProfileForm`:

- `POST /profiles/public`: `@ModelAttribute("publicProfile")`. Chỉ được bind `nickname`, không cho sửa `bio` hoặc `role`. Có thêm validator cấm nickname `guest` ở ngữ cảnh công khai.
- `POST /profiles/private`: `@ModelAttribute("privateProfile")`. Cho bind `nickname` và `bio`, nhưng không cho bind `role`.
- Một `@InitBinder({"publicProfile","privateProfile"})` đăng ký `StringTrimmerEditor` dùng chung, cho phép quan sát **một init binder có nhiều tên**.
- Hai bên vẫn nhận `@NotBlank` của Jakarta Validation từ cùng Java class.

**Điểm học tập:** chỉ đổi **tên model attribute**, không cần đổi kiểu form, nhưng các scoped init binders có thể áp dụng chính sách khác nhau. Ví dụ chỉ mô phỏng binding và trả JSON; không thực sự ghi database. Khi có client gửi field ngoài allowlist, controller minh họa việc trả 400 thay vì im lặng bỏ qua.

### 5.1. Cấu trúc thư mục

```text
scoped-initbinder-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── ScopedBinderApplication.java
    │   ├── ProfileForm.java
    │   ├── PublicProfileValidator.java
    │   └── ProfileController.java
    └── test/java/demo/
        └── ProfileControllerTest.java
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
    <artifactId>scoped-initbinder-demo</artifactId>
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

Dùng Java 17 và Spring Boot 3.4.5 để thống nhất Spring Framework 6.x + Jakarta Validation API. `spring-boot-starter-web` tạo MVC stack, không dùng WebFlux cho ví dụ này. `spring-boot-starter-validation` cung cấp Jakarta Validation provider; `spring-boot-starter-test` cung cấp JUnit 5, MockMvc và các assertion.

### 5.3. src/main/java/demo/ScopedBinderApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScopedBinderApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScopedBinderApplication.class, args);
    }
}
```

### 5.4. src/main/java/demo/ProfileForm.java

```java
package demo;

import jakarta.validation.constraints.NotBlank;

public class ProfileForm {

    @NotBlank
    private String nickname;

    private String bio = "unchanged";

    // Cố tình có setter để minh họa mass assignment;
    // không nên bind security-sensitive domain entity trực tiếp.
    private String role = "MEMBER";

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public String getBio() {
        return bio;
    }

    public void setBio(String bio) {
        this.bio = bio;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }
}
```

Class là JavaBean có constructor không tham số ngầm định và getter/setter public. Initial state `bio="unchanged"`, `role="MEMBER"` giúp kiểm tra field bị suppress **không bị ghi đè**. `@NotBlank` là constraint chung cho cả hai form, bởi cùng dùng kiểu `ProfileForm`.

Trong production, nên dùng DTO **không có setter role** nếu endpoint tuyệt đối không được nhận role. Field nhạy cảm ở đây có chủ đích để minh họa hiệu quả `allowedFields` và `BindingResult#getSuppressedFields()`.

### 5.5. src/main/java/demo/PublicProfileValidator.java

```java
package demo;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class PublicProfileValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return ProfileForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ProfileForm form = (ProfileForm) target;

        if ("guest".equalsIgnoreCase(form.getNickname())) {
            errors.rejectValue(
                    "nickname",
                    "nickname.reservedForPublic",
                    "Public nickname is reserved"
            );
        }
    }
}
```

Đây là Spring `Validator`, không phải Jakarta `ConstraintValidator`. Nó được **đăng ký chỉ trên binder publicProfile**, nên chỉ được Spring tự chạy khi bind/validate public form. Nó ghi một field error qua `Errors.rejectValue(...)`, không ném exception để thay thế cơ chế binding.

`supports(ProfileForm.class)` trả true. Nếu cùng Java class được bind dưới tên `privateProfile`, validator này **không được đăng ký bởi binder private**, dù kiểu form giống hệt.

### 5.6. src/main/java/demo/ProfileController.java

```java
package demo;

import jakarta.validation.Valid;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    // Chỉ binder có objectName = "publicProfile".
    @InitBinder("publicProfile")
    public void publicBinder(WebDataBinder binder) {
        binder.setAllowedFields("nickname");
        binder.addValidators(new PublicProfileValidator());
    }

    // Chỉ binder có objectName = "privateProfile".
    @InitBinder("privateProfile")
    public void privateBinder(WebDataBinder binder) {
        binder.setAllowedFields("nickname", "bio");
    }

    // Áp dụng cho hai objectName kể trên; không phụ thuộc endpoint path.
    @InitBinder({"publicProfile", "privateProfile"})
    public void commonProfileBinder(WebDataBinder binder) {
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(false));
    }

    @PostMapping(
            path = "/profiles/public",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> updatePublic(
            @Valid @ModelAttribute("publicProfile") ProfileForm form,
            BindingResult result) {

        return respond(form, result);
    }

    @PostMapping(
            path = "/profiles/private",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> updatePrivate(
            @Valid @ModelAttribute("privateProfile") ProfileForm form,
            BindingResult result) {

        return respond(form, result);
    }

    private ResponseEntity<?> respond(
            ProfileForm form, BindingResult result) {

        if (result.getSuppressedFields().length > 0) {
            List<String> names = Arrays.stream(
                    result.getSuppressedFields()).sorted().toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "code", "DISALLOWED_FIELDS",
                    "suppressed", names
            ));
        }

        if (result.hasErrors()) {
            List<String> fields = result.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "code", "INVALID_PROFILE",
                    "fields", fields
            ));
        }

        // Kiểm thử trạng thái cuối sau binding; không lưu DB.
        return ResponseEntity.ok(Map.of(
                "code", "OK",
                "nickname", form.getNickname(),
                "bio", form.getBio(),
                "role", form.getRole()
        ));
    }
}
```

**Giải thích từng annotation và lệnh:**

1. `@InitBinder("publicProfile")` chỉ thay đổi binder của `@ModelAttribute("publicProfile")`. Tên field được phép là `nickname`.
2. `@InitBinder("privateProfile")` chỉ thay đổi binder của `@ModelAttribute("privateProfile")`. Cho phép thêm `bio` nhưng không cho `role`.
3. `@InitBinder({"publicProfile","privateProfile"})` áp dụng cho **cả hai**, đăng ký một `StringTrimmerEditor(false)`. Nó loại bỏ whitespace hai đầu của String được bind mà **không đổi chuỗi rỗng thành null**.
4. Hai endpoint đều dùng **cùng một `ProfileForm.class`**, nên kết quả khác nhau là do **binder objectName**, không phải kiểu Java.
5. `@Valid` trên hai đối số `@ModelAttribute` kích hoạt validation. Public binder có Spring `PublicProfileValidator` bổ sung; cả hai có `@NotBlank` nếu cấu hình Jakarta Validation được kích hoạt.
6. `BindingResult` đặt **ngay sau** form object để nhận lỗi binding/validation. `getSuppressedFields()` báo các field bị từ chối trong property binding; chúng **không tự nhất thiết là FieldError**.
7. Demo trả HTTP 400 khi có suppressed fields, thay vì chỉ bỏ qua dữ liệu lạ. Nó dùng allowlist rõ ràng và tránh đưa **raw rejected values** vào response.
8. Trong thực tế, nên tổ chức business logic, authorization và persistence riêng; controller này cố ý không ghi database để ví dụ chỉ kiểm tra **scope của binder**.

**Quan trọng về bảo mật:** các tên URL `/profiles/public` và `/profiles/private` không tự tạo binder scope. Đường URL chỉ chọn **controller method**; tên trong `@ModelAttribute("...")` mới quyết định binder nào nhận cấu hình `@InitBinder("...")`.

### 5.7. src/test/java/demo/ProfileControllerTest.java

```java
package demo;

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
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicProfileBindsNicknameAndTrimsString() throws Exception {
        mvc.perform(post("/profiles/public")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("nickname", " Lan "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("OK"))
                .andExpect(jsonPath("$.nickname").value("Lan"))
                .andExpect(jsonPath("$.bio").value("unchanged"))
                .andExpect(jsonPath("$.role").value("MEMBER"));
    }

    @Test
    void privateProfileMayEditBio() throws Exception {
        mvc.perform(post("/profiles/private")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("nickname", "Lan")
                        .param("bio", " About me "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.bio").value("About me"))
                .andExpect(jsonPath("$.role").value("MEMBER"));
    }

    @Test
    void publicProfileRejectsBioEvenWithSameJavaType()
            throws Exception {
        mvc.perform(post("/profiles/public")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("nickname", "Lan")
                        .param("bio", "Should not be changed"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"))
                .andExpect(jsonPath("$.suppressed", hasItem("bio")));
    }

    @Test
    void privateProfileRejectsRole() throws Exception {
        mvc.perform(post("/profiles/private")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("nickname", "Lan")
                        .param("role", "ADMIN"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("DISALLOWED_FIELDS"))
                .andExpect(jsonPath("$.suppressed", hasItem("role")));
    }

    @Test
    void publicProfileHasItsOwnSpringValidator() throws Exception {
        mvc.perform(post("/profiles/public")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("nickname", "guest"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_PROFILE"))
                .andExpect(jsonPath("$.fields", hasItem("nickname")));
    }

    @Test
    void privateProfileDoesNotRunPublicPolicy() throws Exception {
        mvc.perform(post("/profiles/private")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("nickname", "guest"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nickname").value("guest"));
    }

    @Test
    void jakartaNotBlankAppliesToPublicForm() throws Exception {
        mvc.perform(post("/profiles/public")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("nickname", "   "))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_PROFILE"))
                .andExpect(jsonPath("$.fields", hasItem("nickname")));
    }

    @Test
    void jakartaNotBlankAppliesToPrivateForm() throws Exception {
        mvc.perform(post("/profiles/private")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("nickname", "   "))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields", hasItem("nickname")));
    }
}
```

Bộ test kiểm tra **cùng class, khác objectName**, gồm tám tình huống:

- Public chỉ cho thay nickname và trim whitespace.
- Private cho thay bio, trim whitespace.
- Field bio bị suppress trong public form.
- Field role bị suppress trong private form.
- Spring Validator riêng public cấm nickname `guest`.
- Private form không chạy Spring Validator riêng public.
- Jakarta `@NotBlank` vẫn chạy cho public.
- Jakarta `@NotBlank` vẫn chạy cho private.

Chạy ở thư mục project, dùng Java 17+ và Maven:

```bash
mvn -q test
```

**Kết quả dự kiến:** cả tám test thành công, Maven kết thúc với exit code 0 khi dependency tải đầy đủ. Không đưa “stdout chính xác” cho Maven vì Spring, JUnit và Surefire có thể ghi log khác nhau. Nội dung khẳng định của từng test đã được chỉ rõ bằng `status()` và `jsonPath(...)`; ví dụ chưa được chạy trong môi trường máy thực tế ở đây.

Chạy server:

```bash
mvn spring-boot:run
```

Gửi request form từ shell POSIX:

```bash
curl -i -X POST 'http://localhost:8080/profiles/public' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'nickname=Lan'

curl -i -X POST 'http://localhost:8080/profiles/public' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'nickname=Lan' \
  --data-urlencode 'bio=Hello'

curl -i -X POST 'http://localhost:8080/profiles/private' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'nickname=Lan' \
  --data-urlencode 'bio=Hello'
```

Các request dự kiến nhận status **200**, **400**, **200**. Response thứ hai có mã `DISALLOWED_FIELDS` và tên `bio` trong `suppressed`, trong khi request cuối có thể cập nhật `bio`. Trong JSON object, thứ tự keys không được bảo đảm.

Response thành công của request public đầu tiên có dạng:

```json
{
  "code": "OK",
  "nickname": "Lan",
  "bio": "unchanged",
  "role": "MEMBER"
}
```

Response lỗi khi public cố thay bio:

```json
{
  "code": "DISALLOWED_FIELDS",
  "suppressed": ["bio"]
}
```

Response thành công khi private được sửa bio:

```json
{
  "code": "OK",
  "nickname": "Lan",
  "bio": "Hello",
  "role": "MEMBER"
}
```

Đây là output theo **hợp đồng demo**; kết quả chỉ chứng minh binding và rule áp dụng đúng tên. Nó không thay thế authorization để xác nhận người dùng được phép sửa hồ sơ cụ thể.

## 6. Thứ tự và sự tương tác của nhiều @InitBinder

Một binder có thể nhận nhiều initializer:

```java
@InitBinder
void general(WebDataBinder binder) {
    binder.setAutoGrowCollectionLimit(32);
}

@InitBinder("publicProfile")
void publicOnly(WebDataBinder binder) {
    binder.setAllowedFields("nickname");
}

@InitBinder({"publicProfile", "privateProfile"})
void shared(WebDataBinder binder) {
    binder.registerCustomEditor(
            String.class, new StringTrimmerEditor(false));
}
```

Ba fragment trên minh họa **các cấu hình không xung đột**. Method không chỉ định tên (general) áp dụng rộng; publicOnly giới hạn public; shared giới hạn hai tên.

**Không thiết kế nhiều initializer cùng gọi `setAllowedFields(...)` với các danh sách không tương thích rồi phỏng đoán Spring sẽ tự hợp nhất.** Method setter đặt lại chính sách của binder; nếu cùng setter chạy nhiều lần, giá trị cuối cùng phụ thuộc thứ tự áp dụng. Với `@ControllerAdvice` và local controller, Spring MVC áp dụng global init-binder trước local, nhưng vẫn nên chủ động tránh xung đột và test hành vi.

Một cách tổ chức ổn định:

- Đặt conversion/formatting chung ở global `FormattingConversionService` hoặc `@InitBinder` không xung đột.
- Đặt allowlist đặc thù vào **một** scoped binder sở hữu chính sách cho objectName.
- Đặt Spring Validator đặc thù cho target objectName tương ứng.
- Không lặp lại allowlist khác nhau trong nhiều `@ControllerAdvice` thiếu quy định precedence rõ ràng.
- Với nhiều form cùng Java class, đặt tên tường minh và viết test so chéo để phát hiện binder config bị lan sang form khác.

### 6.1. Phương thức cùng tên trong controller khác

Một `@InitBinder("publicProfile")` khai báo bên trong `ProfileController` không tự áp dụng cho `OtherController`, dù OtherController cũng có model attribute tên `publicProfile`. Phạm vi **local controller** vẫn có hiệu lực.

Ngược lại, cùng method đó được đặt trong `@ControllerAdvice` áp dụng toàn cục thì **mọi controller được advice chọn** có binder tên `publicProfile` đều có thể nhận config. Nếu hai tính năng cùng dùng tên `publicProfile` nhưng domain semantics khác, điều này có thể gây bất ngờ.

### 6.2. Chọn subset controllers bằng @ControllerAdvice

Ví dụ fragment:

```java
@ControllerAdvice(
    basePackageClasses = ProfileController.class
)
public class ProfileBinderAdvice {

    @InitBinder("publicProfile")
    void configure(WebDataBinder binder) {
        binder.setAllowedFields("nickname");
    }
}
```

Đây là **ví dụ giải thích scope**, không thêm vào project runnable ở mục 5 vì nó lặp chính sách `setAllowedFields` của local controller. `basePackageClasses` chọn **các controller trong package**, còn `@InitBinder("publicProfile")` chọn **tên binder**. Không nhầm với `assignableTypes` (chọn class/controller types cụ thể) và `annotations` (chọn controller có annotation).

Nếu chỉ muốn scope vào **đúng một controller**, dùng `@ControllerAdvice(assignableTypes=ProfileController.class)` là minh họa rõ hơn so với `basePackageClasses` vốn chọn cả package.

## 7. @InitBinder và @ModelAttribute có quan hệ tên nhưng không thay nhau

`@ModelAttribute` có thể làm hai việc:

1. Trên **method**: thêm attribute vào model, thường trước khi xử lý request method.
2. Trên **method parameter**: lấy/tạo attribute, bind request và có thể validate.

Ví dụ hai fragment độc lập:

```java
@ModelAttribute("publicProfile")
public ProfileForm makeForm() {
    return new ProfileForm();
}

@PostMapping("/profiles/public")
public String save(
        @Valid @ModelAttribute("publicProfile") ProfileForm form,
        BindingResult errors) {
    return errors.hasErrors() ? "profile-form" : "saved";
}
```

Trong luồng này `@InitBinder("publicProfile")` sẽ áp vào binder khi Spring xử lý attribute cùng tên. Dùng `@ModelAttribute("publicProfile")` trên **parameter** là cách xác định binder objectName rõ nhất.

**Không nhầm tên JSP/Thymeleaf variable với Java type**: view template có thể dùng `modelAttribute="publicProfile"` hoặc `th:object` trỏ vào model đó. Tên này nên nhất quán xuyên suốt rendering, binding, validation và @InitBinder.

### Khi dùng @ModelAttribute(binding=false)

```java
@ModelAttribute(binding = false)
ProfileForm existingProfile
```

Đây là fragment. Nó yêu cầu Spring không thực hiện data binding từ request parameters cho attribute đó. Vì vậy không nên mong `setAllowedFields(...)` có tác dụng “cập nhật field” trên parameter đang đặt `binding=false`. Nhưng binder có thể vẫn được tạo vì những mục đích khác tùy pipeline; nếu cần ngăn mutating dữ liệu, xem xét cả logic controller và DTO/authorization.

## 8. Phân biệt property binding, constructor binding và phạm vi allowedFields

Bài này sử dụng **JavaBean với constructor rỗng và setters public**, nên `setAllowedFields` có hiệu lực dễ quan sát với **property binding**. Spring Framework 6.x cũng có **constructor binding**, trong đó đối số constructor có thể được lấy từ request parameters.

Lưu ý bảo mật quan trọng:

- `setAllowedFields(...)` định giới hạn cho **property binding**. Đừng suy rằng nó tự chặn mọi constructor argument của tất cả kiểu DTO trong mọi trường hợp.
- Với immutable DTO/record, hãy thiết kế constructor nhận **chỉ dữ liệu mà request có quyền cung cấp**.
- Nếu muốn cấu hình theo hướng “constructor binding only” khi phù hợp, Spring có `binder.setDeclarativeBinding(true)`; lúc đó property binding chỉ diễn ra khi cấu hình allowedFields, nhưng phải kiểm tra phiên bản và contract cụ thể.
- Đặt tên object đúng bảo đảm **chọn initializer**, không tự bảo đảm form có sơ đồ thuộc tính an toàn. Cần DTO chuyên dụng, allowlist và kiểm tra authorization ở server.
- `@InitBinder("publicProfile")` không cấm người dùng gửi raw HTTP field `role=ADMIN`. Nó điều chỉnh binder: field không được phép sẽ bị suppress trong property-binding phase, và application nên xem `BindingResult#getSuppressedFields()` khi quyết định có reject request hay không.

### Mẫu chống mass assignment

Nếu server có entity chứa role, balance, ownerId hay status, **không nên bind trực tiếp entity đó với mặc định mọi field được phép**:

```java
// Nguy hiểm nếu OrderEntity có setter cho các field nhạy cảm.
@PostMapping("/orders")
public void update(@ModelAttribute OrderEntity entity) {
    // ...
}
```

Đây là fragment minh họa **anti-pattern**; không có project runnable kèm theo. Tối thiểu nên dùng DTO chỉ chứa field được phép và map có kiểm soát vào entity sau authorization. Nếu vẫn cần setter binding, dùng `@InitBinder("orderForm")` với allowlist, và test các trường bị suppress.

## 9. @InitBinder không phải bộ lọc toàn HTTP request

Các khái niệm cần phân biệt:

| Thành phần | Dùng để làm gì | Điểm dễ nhầm |
| --- | --- | --- |
| `@InitBinder("publicProfile")` | Chọn binder dựa trên objectName | Không chọn HTTP endpoint theo path |
| `@ModelAttribute("publicProfile")` | Đặt tên command/model attribute | Không tự áp allowlist |
| `setAllowedFields("nickname")` | Giới hạn property paths được gắn | Không chọn binder theo objectName |
| `@ControllerAdvice(assignableTypes=...)` | Chọn controller nhận advice | Không chọn field trong object |
| `@Valid` / `@Validated` | Yêu cầu validation theo constraint hoặc hints | Không thay thế cấu hình binder |
| `BindingResult` | Đọc lỗi binding/validation, suppressed fields | Không tự chặn request nếu code bỏ qua |
| `@RequestBody` + Jackson | Deserialize JSON theo HTTP message converter | Không dùng `allowedFields` như cơ chế property binding JSON |
| `@RequestParam` | Resolve query/form parameter đơn lẻ | Không phải tên model attribute trừ khi binder cho parameter đó dùng đúng tên |

### Đặc biệt: @RequestBody JSON

Một JSON body thường được Jackson deserialize thành DTO, sau đó Spring có thể tạo binder để **validation** nếu controller dùng `@Valid`. Nhưng `binder.setAllowedFields(...)` không có nghĩa Jackson bỏ các JSON properties trước khi tạo object như với `@ModelAttribute` property binding.

Không dùng scoped `@InitBinder` để thay thế DTO schema, Jackson configuration, validation và authorization của JSON API. Với REST JSON, nên ưu tiên command DTO rõ ràng và kiểm soát các properties được deserialize ngay từ thiết kế object/serializer. Scoped binder vẫn có giá trị cho **custom validator** khi objectName của binder phù hợp.

### Đặc biệt: @RequestParam

Javadoc `@InitBinder` cho phép chỉ định tên của **request parameters**, ngoài tên form attributes. Tuy nhiên nó chọn **binder có tên tương ứng**, không phải cơ chế “chỉ đọc key này khỏi mọi request”. Trên controller có tham số riêng lẻ, loại binding/conversion và objectName phải được xác định theo handler argument resolver thực tế; nếu cần custom type conversion áp dụng nhất quán rộng, cân nhắc `ConversionService` thay vì phỏng đoán selector của `@InitBinder`.

## 10. Debug lỗi @InitBinder không được gọi

### 10.1. Tên không khớp

```java
@InitBinder("userForm")
void configure(WebDataBinder binder) { /* ... */ }

@PostMapping("/users")
String save(@ModelAttribute("user") UserForm user) {
    return "done";
}
```

Hai tên `userForm` và `user` khác nhau. Binder cho `@ModelAttribute("user")` không chọn initializer `@InitBinder("userForm")`. Cách sửa là **đồng nhất tên**, không đổi field trong Java class.

### 10.2. Khác chữ hoa/thường

`@InitBinder("PublicProfile")` khác `@ModelAttribute("publicProfile")`. Spring không tự lowercase model attribute names khi so khớp selector tường minh.

### 10.3. Dùng tên class thay cho tên model attribute

`@InitBinder("ProfileForm")` không được bảo đảm khớp với `@ModelAttribute("publicProfile") ProfileForm form`. Java class tên `ProfileForm` chỉ mô tả kiểu của target, còn objectName là `publicProfile`.

### 10.4. Method nằm trong sai controller

Nếu initializer khai báo trong `SettingsController` mà handler ở `ProfileController`, method local không tự áp dụng xuyên controller. Dùng `@ControllerAdvice` nếu thật sự muốn chia sẻ, rồi giới hạn cả target controllers lẫn object names.

### 10.5. Multiple initializers chồng nhau

Một `@InitBinder` không tên và một `@InitBinder("publicProfile")` có thể cùng chạy. Nếu cả hai cùng gọi `setAllowedFields`, hãy kiểm tra thứ tự/cấu hình thay vì nghĩ scoped binder tự “ghi đè an toàn” theo ý bạn. Trong ví dụ runnable, common binder chỉ đăng ký `StringTrimmerEditor` để tránh xung đột.

### 10.6. Spring Validator không chạy

Đăng ký `binder.addValidators(...)` là một bước; cần có cơ chế **yêu cầu validation** trên đối số, ví dụ `@Valid`/`@Validated`, hoặc lời gọi `binder.validate()` nếu bạn tự thao tác binder. Kiểm tra `supports(...)` của validator và tên target đúng. Nếu chỉ dùng `@ModelAttribute` không có yêu cầu validation, không nên tự suy custom validator luôn chạy.

### 10.7. Bị nhầm với @ControllerAdvice

Method trong `@ControllerAdvice` có thể áp dụng cho nhiều controllers. Để giới hạn, kết hợp `@ControllerAdvice(assignableTypes=...)`/`basePackageClasses`/`annotations` và `@InitBinder("objectName")`. Một điều kiện chọn controller **không thay thế** điều kiện chọn binder name.

### 10.8. Binder có objectName khác tên parameter variable

Đừng log chỉ tên biến Java từ source rồi kết luận. Khi debug bên trong init binder, có thể tạm log:

```java
@InitBinder
void debug(WebDataBinder binder) {
    System.out.println("binder=" + binder.getObjectName());
}
```

Đây là fragment **phục vụ chẩn đoán**, không nên dùng `System.out` trong production. Spring cho phép lấy objectName từ `WebDataBinder`; log objectName là cách kiểm tra trực tiếp giá trị được so khớp. Không log raw request values, token hay object chứa dữ liệu nhạy cảm.

### 10.9. AllowedFields có tác dụng nhưng không tạo FieldError

Các property bị suppress thường có thể lấy qua `result.getSuppressedFields()`. Đừng dựa duy nhất vào `result.hasErrors()` để biết client có cố gửi field ngoài allowlist hay không. Demo đã chủ động trả 400 nếu mảng suppressed không rỗng.

### 10.10. Dùng WebFlux nhưng đọc hướng dẫn MVC

Spring WebFlux annotated controller cũng có `@InitBinder`/`WebDataBinder` và selector model attribute tương tự, nhưng pipeline request khác. Nếu ứng dụng sử dụng Reactor Netty/DispatcherHandler, đừng copy nguyên các phần servlet-specific và test `MockMvc`. Với WebFlux, kiểm thử qua `WebTestClient`, đặc biệt khi dùng request body publisher.

## 11. Các biến thể thực tế

### 11.1. Một validator áp dụng cho một form

```java
@InitBinder("checkoutForm")
void validateCheckout(WebDataBinder binder) {
    binder.addValidators(new CheckoutValidator());
}
```

Cần có `CheckoutValidator` implement Spring `Validator` và `supports(...)` kiểu form; đây chỉ là fragment. Khi form có `@Valid`/`@Validated`, Spring có thể chạy các validators được đăng ký cho binder. Việc scoped bằng tên giúp không tự thêm `CheckoutValidator` vào một command object khác trong controller.

### 11.2. Nhiều form dùng cùng formatter

```java
@InitBinder({"startForm", "endForm"})
void commonDateBinding(WebDataBinder binder) {
    // Đăng ký editor/formatter cho kiểu ngày nếu thật sự cần.
}
```

Fragment này minh họa selector mảng. Khi cần date/time format thống nhất toàn ứng dụng, nên cân nhắc `FormattingConversionService`/`@DateTimeFormat` hơn là lặp cấu hình trong nhiều binder method. Không tạo editor stateful dùng chung giữa request threads nếu nó không thread-safe.

### 11.3. Không có selector nhưng có giới hạn local controller

```java
@Controller
class ShippingController {

    @InitBinder
    void configure(WebDataBinder binder) {
        binder.setAutoGrowCollectionLimit(64);
    }
}
```

Đây là fragment. Không có tên trong `@InitBinder` nghĩa là áp dụng rộng **trong phạm vi của ShippingController**, không phải toàn ứng dụng. Phạm vi global thường đến từ `@ControllerAdvice` hoặc cấu hình khác.

### 11.4. Một controller có hai command objects trên cùng handler

```java
@PostMapping("/combined")
public String combined(
        @ModelAttribute("publicProfile") ProfileForm publicForm,
        BindingResult publicErrors,
        @ModelAttribute("privateProfile") ProfileForm privateForm,
        BindingResult privateErrors) {

    if (publicErrors.hasErrors() || privateErrors.hasErrors()) {
        return "combined-form";
    }
    return "done";
}
```

Đây là fragment minh họa, không thuộc controller runnable ở mục 5. Khi một request có hai command objects, Spring có thể tạo **hai binder khác objectName**; mỗi binder nhận đúng initializer. Lưu ý form parameters dùng chung request namespace, nên một key `bio` có thể được xem xét cho cả hai object. **Scoped allowedFields** giúp phân biệt property nào được phép cập nhật, nhưng không tự tạo namespace HTTP riêng. Với form phức tạp, nên thiết kế param names và DTO rõ ràng để tránh tương tác không mong đợi.

## 12. Câu hỏi thường gặp

**Hỏi: `@InitBinder("publicProfile")` có nghĩa chỉ chạy với URL `/profiles/public`?**

Không. Nó so khớp **binder objectName**, không so URL. Handler ở URL khác cũng dùng `@ModelAttribute("publicProfile")` có thể nhận cùng initializer nếu nằm trong phạm vi controller/advice phù hợp.

**Hỏi: Cùng class `ProfileForm` thì có được khai báo hai tên binder không?**

Có. Ví dụ runnable cố ý dùng cùng class cho `publicProfile` và `privateProfile`. Cấu hình vẫn khác theo tên, chứng minh selector không dựa trên Java type.

**Hỏi: Có thể giới hạn một `@InitBinder` cho nhiều object names không?**

Có: `@InitBinder({"publicProfile", "privateProfile"})`. Mỗi tên được so khớp, không phải tạo binder hợp nhất.

**Hỏi: Nếu bỏ `value` thì chỉ áp dụng cho model attribute tên mặc định à?**

Không. `@InitBinder` không tên là wildcard **trong phạm vi controller/advice**, áp dụng cho binder phù hợp nói chung. Nó không có điều kiện tên cụ thể.

**Hỏi: Có thể gắn `@InitBinder` lên method request handler không?**

Về mục đích API, nó đánh dấu **initializer method**, thường là một method riêng nhận `WebDataBinder` và trả `void`. Không coi nó là handler trả response hoặc thay thế `@PostMapping`.

**Hỏi: `setAllowedFields` có phải là validation rule của Jakarta Bean Validation không?**

Không. Nó giới hạn **property assignment** khi binding. Các constraint như `@NotBlank` được xử lý bởi validator; `BindingResult` có thể chứa lỗi từ cả binding lẫn validation.

**Hỏi: Dùng `@RequestBody` JSON có chặn được field `role` bằng `setAllowedFields` không?**

Không nên dựa vào đó. Jackson deserialization không tương đương WebDataBinder property binding. Sử dụng DTO riêng, constructor/record chỉ chứa field hợp lệ, Jackson configuration và authorization.

**Hỏi: `@ControllerAdvice` có cho mọi controller dùng `@InitBinder("publicProfile")` không?**

Theo mặc định, advice có thể áp dụng rộng cho các controller, nhưng vẫn phải **khớp objectName**; có thể giới hạn advice bằng các selector controller nếu cần. Nếu cùng tên được dùng ở nhiều ngữ cảnh, cân nhắc tên rõ nghĩa hơn hoặc hạn chế tập controller.

## 13. Checklist kiểm tra trước khi triển khai

- [ ] Xác định **đối tượng/form cụ thể** cần tùy biến binder.
- [ ] Đặt tên tường minh trên `@ModelAttribute("objectName")` của handler.
- [ ] Dùng đúng chuỗi, đúng chữ hoa/thường trong `@InitBinder("objectName")`.
- [ ] Nếu một cấu hình dùng cho nhiều object, khai báo `@InitBinder({"a","b"})`.
- [ ] Phân biệt phạm vi **local controller** và phạm vi **@ControllerAdvice**.
- [ ] Không dùng selector tên để thay thế allowlist property binding.
- [ ] Đặt `allowedFields` cho field được phép nếu dùng setter/property binding với dữ liệu không tin cậy.
- [ ] Dùng DTO chuyên dụng hoặc constructor binding an toàn cho dữ liệu nhạy cảm.
- [ ] Nếu thêm custom Spring Validator, kiểm tra `supports` và việc kích hoạt `@Valid`/`@Validated`.
- [ ] Tránh cấu hình cùng thuộc tính binder theo nhiều method có khả năng xung đột.
- [ ] Đặt `BindingResult` ngay sau model argument để nhận và phân loại lỗi phù hợp.
- [ ] Kiểm tra `getSuppressedFields()` và chủ động xử lý request có field không được phép nếu hợp đồng yêu cầu.
- [ ] Viết test **hai object cùng type nhưng khác tên**: mỗi object chỉ nhận đúng cấu hình của mình.
- [ ] Thử name mismatch, field không được phép, validation riêng từng form, dữ liệu hợp lệ và data conversion.
- [ ] Kiểm tra lại nếu di chuyển initializer từ controller sang `@ControllerAdvice`.

## 14. Kết luận

**`@InitBinder("objectName")` giới hạn phương thức khởi tạo WebDataBinder theo tên của command/form attribute hoặc request parameter target**. Không có tên → cấu hình áp dụng rộng trong scope controller/advice. Một tên → chỉ binder đó. Nhiều tên → một trong các binder tương ứng.

Điều này cho phép **cùng controller, thậm chí cùng Java class**, có các chính sách bind/validate khác nhau cho từng model attribute. Chìa khóa của thiết kế dễ hiểu là **đặt tên `@ModelAttribute` tường minh**, tránh chồng chéo initializer, dùng DTO/allowlist để bảo vệ dữ liệu, và kiểm thử hành vi trên chính các endpoint mà Spring MVC thực sự xử lý.

## Tài liệu tham khảo

- [Spring Framework 6.2 — @InitBinder trong Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — @ControllerAdvice và thứ tự global/local](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html)
- [Spring Framework 6.2 — @ModelAttribute method arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — MVC Data Binding / Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-data-binding.html)
- [Spring Framework — @InitBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/annotation/InitBinder.html)
- [Spring Framework — InitBinderDataBinderFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/method/annotation/InitBinderDataBinderFactory.html)
- [Spring Framework — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/BindingResult.html)

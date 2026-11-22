# @InitBinder trong @Controller — Tùy biến binding và validation ở Spring MVC

## 1. Vấn đề mà `@InitBinder` giải quyết

Khi một form gửi dữ liệu tới Spring MVC, các giá trị đến từ HTTP ban đầu thường là **chuỗi**. Framework phải lấy field theo tên, chuyển kiểu và đưa vào một đối tượng Java trước khi controller dùng đối tượng đó:

```http
POST /profiles/form
Content-Type: application/x-www-form-urlencoded

displayName=%20%20Linh%20%20&email=linh%40example.com&appointmentDate=31%2F12%2F2026&admin=true
```

Ví dụ, DTO có `String displayName`, `String email`, `LocalDate appointmentDate` và `boolean admin`. Ta muốn:

- Chuẩn hóa `displayName` bằng cách cắt khoảng trắng hai đầu.
- Giải mã ngày theo chuỗi `dd/MM/uuuu`, thay vì ISO mặc định.
- Chỉ cho phép client sửa `displayName`, `email` và `appointmentDate`; **không** cho form tự thay `admin`.
- Đăng ký một validator dùng riêng ở controller đó, kết hợp với Jakarta Validation.
- Khi lỗi xảy ra, phân biệt lỗi **binding** (chuyển kiểu), lỗi **validation** (constraint) và field đã bị **suppressed** (bị chặn bởi allowlist).

`@InitBinder` chính là điểm cấu hình **`WebDataBinder`** trước khi Spring dùng binder ở những request argument phù hợp. Nó không tự làm mọi thao tác trên: nó chỉ cài đặt chính sách cho binder, còn việc bind/validate được hệ thống xử lý ở bước tiếp theo.

**Mục tiêu học tập:** hiểu vòng đời `@InitBinder`, phạm vi controller và model attribute, các thao tác thường dùng trên `WebDataBinder`, cách phối hợp `@ModelAttribute`/`@Valid`/`BindingResult`, giới hạn khi gặp `@RequestBody`, và kiểm thử được hành vi này bằng Java 17 + Spring Boot + MockMvc.

> **Phạm vi:** Spring MVC Servlet stack, Jakarta Validation, Spring Framework 6.2.x / Spring Boot 3.5.x. WebFlux cũng có khái niệm binder nhưng luồng xử lý và exception khác; không nên mặc nhiên áp dụng chữ ký Servlet MVC cho WebFlux.

## 2. `WebDataBinder` là gì?

`org.springframework.web.bind.WebDataBinder` là binder dành cho môi trường web, kế thừa `org.springframework.validation.DataBinder`. Nó có thể tham gia:

1. **Binding:** gán các request parameters/form fields vào property hoặc constructor arguments của object đích.
2. **Conversion:** chuyển `String` thành `int`, `LocalDate`, enum, kiểu tùy chỉnh...
3. **Formatting:** đọc chuỗi theo format riêng và có thể định dạng giá trị để hiển thị lại trong form.
4. **Validation:** sử dụng các `org.springframework.validation.Validator` đã đăng ký khi validation được kích hoạt.
5. **Binding policy:** giới hạn field cho phép, đánh dấu field bắt buộc, cấu hình auto-grow nested paths/collections.

`@InitBinder` là method mà Spring MVC gọi để **cấu hình binder**, không phải phương thức endpoint nhận HTTP request. Một binder được gắn với ngữ cảnh target/object name phù hợp; không nên lưu nó vào static field hoặc một singleton tùy ý.

Ví dụ tối giản:

```java
@Controller
public class RegistrationController {

    @InitBinder
    void configure(WebDataBinder binder) {
        binder.setAllowedFields("name", "email");
    }

    @PostMapping("/register")
    String register(@ModelAttribute RegistrationForm form) {
        // ...
        return "success";
    }
}
```

Đây là **đoạn minh họa**, chưa có định nghĩa `RegistrationForm` hay toàn bộ imports. Khi Spring bind form ở controller này, những property không có trong allowlist không được setter-binding. `@InitBinder` không tự trả `"success"`, không xử lý request thay cho `@PostMapping` và không tự ném Bean Validation violation.

## 3. Vòng đời: Spring gọi `@InitBinder` vào lúc nào?

Khái quát cho một form thuộc `@ModelAttribute`:

```text
HTTP request
   |
   v
DispatcherServlet chọn @Controller + handler method
   |
   v
Argument resolver chuẩn bị model attribute
   |
   v
WebDataBinderFactory tạo WebDataBinder
   |
   +--> @InitBinder trong @ControllerAdvice (nếu áp dụng)
   |
   +--> @InitBinder trong @Controller (nếu áp dụng)
   |
   v
Binder thực hiện constructor/property binding và conversion
   |
   +--> Lỗi chuyển kiểu -> BindingResult FieldError
   |
   +--> Field không được phép -> suppressed fields
   |
   v
Nếu @Valid / @Validated kích hoạt -> binder.validate(...)
   |
   +--> Lỗi constraint -> BindingResult FieldError/ObjectError
   |
   v
Handler nhận object và BindingResult (nếu khai báo)
```

Đây là **mô hình học tập**; một số chi tiết như constructor binding và thời điểm lấy target phụ thuộc argument resolver và model attribute. Điểm cốt lõi: `@InitBinder` cấu hình chính sách **trước khi binder thực hiện tác vụ tương ứng**.

Với mỗi request, có thể có nhiều binder dành cho các đối tượng/arguments khác nhau. Spring có thể gọi `@InitBinder` nhiều lần nếu handler cần nhiều binder. Vì vậy method này nên **nhanh, không side effect, không phụ thuộc vào việc chỉ được gọi đúng một lần**.

### 3.1. Một phương thức `@InitBinder` hợp lệ

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("name", "email");
}
```

Nó thường:
- Có return type `void`.
- Nhận `WebDataBinder`, có thể thêm một số argument được Spring hỗ trợ cho binder initialization.
- Dùng để đăng ký editor, formatter, converter, validator hoặc chính sách.
- Không phải `@RequestMapping`, không cần thêm URL.
- Không nhận command object thông qua argument `@ModelAttribute` như một handler bình thường; Spring docs loại trừ `@ModelAttribute` khỏi các argument được hỗ trợ của method `@InitBinder`.

## 4. Phạm vi áp dụng: controller, model attribute và controller advice

### 4.1. `@InitBinder` không có giá trị chỉ rõ tên

```java
@RestController
public class FormController {

    @InitBinder
    void configure(WebDataBinder binder) {
        binder.setAllowedFields("name", "email");
    }
}
```

Cấu hình thuộc **controller này**, không tự lan sang mọi controller của ứng dụng. Vì không có tên attribute trong annotation, nó có thể áp dụng cho các binder liên quan tới handler methods thuộc controller này, nên hãy tránh đặt một allowlist chỉ hợp với một DTO nếu controller có nhiều DTO khác nhau.

### 4.2. `@InitBinder("profileForm")` — giới hạn theo object name

```java
@InitBinder("profileForm")
void configureProfile(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email", "appointmentDate");
}

@PostMapping("/profiles")
public ResponseEntity<?> create(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {
    // ...
}
```

**Điểm nối chính xác:** chuỗi `"profileForm"` trên `@InitBinder` phải khớp **model attribute name** mà binder đang xử lý. Tên này không phải URL, cũng không phải tên method Java. Khai báo tường minh `@ModelAttribute("profileForm")` tránh phụ thuộc tên được suy ra và rất hữu ích khi controller có nhiều form.

Có thể dùng `@InitBinder({"profileForm", "settingsForm"})` để áp dụng cho hai object names. Không nên đoán rằng annotation nào cũng bind theo tên class hoặc tên biến Java: tên object thực tế mới quyết định việc chọn binder.

### 4.3. `@ControllerAdvice` — cấu hình dùng chung nhiều controller

```java
@ControllerAdvice
public class CommonBindingAdvice {

    @InitBinder
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

Đây là **đoạn cấu hình minh họa**, không nằm trong project chạy ở phần 9. Khi đặt `@InitBinder` trong `@ControllerAdvice`, Spring có thể áp dụng nó cho nhiều controller; `@ControllerAdvice` cũng có các thuộc tính lựa chọn như `basePackages`, `annotations`, `assignableTypes` để giới hạn phạm vi.

Chọn vị trí theo mục đích:
- Quy tắc riêng cho một form/controller → `@InitBinder` ở controller và, nếu cần, chỉ định object name.
- Quy tắc thống nhất cho nhiều endpoint → `@ControllerAdvice` hoặc MVC config/`ConversionService`.
- Quy tắc chuyển đổi một kiểu dữ liệu dùng rộng rãi → thường nên đăng ký `Converter`/`Formatter` toàn cục thay vì sao chép logic ở từng controller.

Không tạo một global allowlist có thể làm các DTO khác mất field nếu không nắm rõ mọi object name mà advice sẽ xử lý.

## 5. `setAllowedFields` và bảo vệ trước mass assignment

### 5.1. Vấn đề setter binding mặc định

Nếu một DTO có property `admin` với setter public:

```java
public class ProfileForm {
    private String displayName;
    private boolean admin;

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

và ứng dụng bind form qua setters, client có thể thử gửi `admin=true` dù HTML ban đầu không hiển thị input này. Việc trường bị ẩn trên UI **không** phải biện pháp bảo vệ dữ liệu. Đây là ví dụ về **mass assignment / over-posting**.

Với `@InitBinder`:

```java
@InitBinder("profileForm")
void restrict(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "email", "appointmentDate");
}
```

chỉ những tên field đã cho phép mới được property binding thông thường. Field `admin` bị **suppressed** thay vì gán thành `true` từ request. Những field bị suppressed có thể được xem qua:

```java
String[] suppressed = bindingResult.getSuppressedFields();
```

`BindingResult` là object đọc lỗi/binding ở handler, **không phải** tham số của `@InitBinder`.

**Lưu ý bảo mật:** Ví dụ học có `admin` trong DTO để quan sát hiệu ứng chặn. Ứng dụng thật tốt hơn nên dùng **DTO chuyên biệt chỉ chứa các field được phép** và không cho client bind thuộc tính quyền/ID nội bộ. Allowlist là một lớp phòng vệ, không thay authorization trong service.

### 5.2. Allowlist tốt hơn denylist

`binder.setAllowedFields(...)` là *positive allowlist* và **case-sensitive** theo Spring reference. `binder.setDisallowedFields(...)` có thể blacklist những field không muốn bind và xử lý pattern không phân biệt hoa/thường, nhưng khó bảo trì khi model mở rộng. Cách an toàn hơn là chỉ công bố những field có thể sửa, đặc biệt với nested properties.

Ví dụ:

```java
binder.setAllowedFields(
        "contact.email",
        "contact.phone",
        "addresses[0].city");
```

Đây là fragment minh họa. Các chuỗi là **property paths** và có thể dùng wildcard theo API. Trước khi thêm wildcard, hãy đọc kỹ những nested paths thực sự được mở; `"addresses*"` rộng hơn nhiều so với một thuộc tính con cụ thể.

### 5.3. `setDeclarativeBinding(true)` khác gì allowlist?

Trong Spring Framework 6.1+, `WebDataBinder` hỗ trợ:

```java
@InitBinder
void configure(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Khi bật declarative binding, Spring tiếp tục cho phép **constructor binding** với các parameters được định nghĩa trên constructor, còn **property/setter binding** không tự động diễn ra trừ khi có `allowedFields`. Chính sách này đặc biệt phù hợp khi DTO được thiết kế theo immutable constructor hoặc record.

Nếu bạn dùng:

```java
binder.setDeclarativeBinding(true);
binder.setAllowedFields("displayName", "email");
```

thì các trường đã được allowlist vẫn có thể property-bind. **Không hiểu sai** rằng `setAllowedFields` là một bộ lọc chặn mọi constructor argument: constructor binding và property binding là hai kênh khác nhau. Khi cần bảo mật, thiết kế constructor DTO có đúng arguments công khai.

Trong ví dụ hoàn chỉnh ở phần 9, ta dùng mutable form + allowlist để dễ quan sát suppressed fields; **không bật declarativeBinding** trong project đó, vì muốn minh họa rõ setter binding và formatter/editor.

## 6. Chuẩn hóa string với `StringTrimmerEditor`

Một request có:

```text
displayName = "  Linh  "
```

Sau binding có thể muốn:

```text
displayName = "Linh"
```

Trong controller:

```java
@InitBinder("profileForm")
void init(WebDataBinder binder) {
    binder.registerCustomEditor(
            String.class,
            "displayName",
            new StringTrimmerEditor(true));
}
```

Import `org.springframework.beans.propertyeditors.StringTrimmerEditor`. Tham số `true` nghĩa là chuỗi sau trim trở thành **`null` nếu rỗng**; ví dụ `"   "` được chuyển thành null. Nếu dùng `false`, chuỗi toàn khoảng trắng sau trim sẽ là `""` thay vì null.

Tại sao chỉ đăng ký cho `"displayName"`? Vì:

```java
binder.registerCustomEditor(String.class, "displayName", editor);
```

chỉ cài editor cho **property path tương ứng**. Nếu dùng overload `registerCustomEditor(String.class, editor)` không có field name, bạn tác động tới nhiều properties String trong phạm vi binder đó, có thể không phù hợp khi email, password hoặc token có quy tắc whitespace khác nhau.

**Không coi trim là validation.** Sau conversion, `@NotBlank` hoặc custom validator vẫn cần kiểm tra dữ liệu không hợp lệ. Nếu trim tất cả whitespace thành null, `@NotBlank` sẽ phát hiện null; `@NotNull` cũng có thể được sử dụng tùy hợp đồng.

## 7. Formatter và converter: thay đổi cách giải mã kiểu

Form gửi ngày có thể theo định dạng doanh nghiệp:

```text
appointmentDate=31/12/2026
```

Trong Java, thuộc tính đích là `LocalDate`. Nếu không có quy tắc riêng, hệ thống có thể kỳ vọng ISO date như `2026-12-31`; tùy cấu hình MVC và annotation format, chuỗi `31/12/2026` có thể gây type mismatch.

### 7.1. Formatter chỉ áp dụng ở binder của form

```java
@InitBinder("profileForm")
void initProfile(WebDataBinder binder) {
    binder.addCustomFormatter(
            new Formatter<LocalDate>() {

                private final DateTimeFormatter pattern =
                        DateTimeFormatter.ofPattern("dd/MM/uuuu");

                @Override
                public LocalDate parse(String text, Locale locale) {
                    return LocalDate.parse(text, pattern);
                }

                @Override
                public String print(LocalDate date, Locale locale) {
                    return date.format(pattern);
                }
            },
            "appointmentDate");
}
```

Đây là đoạn minh họa cho method `@InitBinder`, cần import `Formatter`, `LocalDate`, `DateTimeFormatter` và `Locale`. `DataBinder.addCustomFormatter(Formatter, String... fields)` giới hạn formatter này vào một property path. `DateTimeFormatter` là immutable/thread-safe và được dùng an toàn qua nhiều request.

Nếu form gửi `31/99/2026`, `LocalDate.parse` không chuyển được dữ liệu; binder ghi nhận lỗi chuyển kiểu trong `BindingResult`. Đó là **binding error**, chưa phải kết quả `@NotNull` hay `@Future` đơn thuần.

### 7.2. Khi chỉ có một field, `@DateTimeFormat` có thể đơn giản hơn

```java
@DateTimeFormat(pattern = "dd/MM/uuuu")
private LocalDate appointmentDate;
```

Đây là phương án có tính khai báo, nên ưu tiên nếu format gắn tự nhiên với field và không cần cấu hình riêng theo controller. Không thêm cả formatter cục bộ và `@DateTimeFormat` vào cùng field mà chưa xem thứ tự ưu tiên: có thể tạo cấu hình chồng chéo khó hiểu.

### 7.3. Editor, Formatter hay Converter?

| Công cụ | Vai trò | Thích hợp khi |
| --- | --- | --- |
| `PropertyEditor` | Hệ thống chuyển kiểu dựa trên `java.beans.PropertyEditor` (Spring wrapper/adapter) | Tùy biến cục bộ, trường hợp tương thích legacy |
| `Formatter<T>` | `parse` từ String, `print` về String, có `Locale` | Định dạng ngày/tiền/số hiển thị trong form |
| `Converter<S,T>` | Chuyển một kiểu nguồn sang một kiểu đích | Quy tắc chuyển kiểu dùng nhiều nơi |
| `FormattingConversionService` toàn cục | Đăng ký chuyển đổi/formatter cho nhiều binders | Toàn ứng dụng có cùng quy ước |
| `@DateTimeFormat` | Format theo annotation field | Một field/type có định dạng rõ ràng |

Đừng dùng `@InitBinder` chỉ để sửa JSON Jackson format; conversion của JSON body đi qua một cơ chế khác, xem phần 11.

## 8. Đăng ký custom validator tại controller

`WebDataBinder` còn cho phép:

```java
@InitBinder("profileForm")
void init(WebDataBinder binder) {
    binder.addValidators(new ProfileFormValidator());
}
```

`ProfileFormValidator` cần implement `org.springframework.validation.Validator`:

```java
public class ProfileFormValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return ProfileForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ProfileForm form = (ProfileForm) target;

        if ("blocked".equalsIgnoreCase(form.getDisplayName())) {
            errors.rejectValue(
                    "displayName",
                    "displayName.blocked",
                    "Tên này không được phép");
        }
    }
}
```

Đây là đoạn minh họa chưa có đầy đủ imports; mã hoàn chỉnh xuất hiện ở phần 9.

- `addValidators` **bổ sung** Spring validator; nó không có nghĩa loại bỏ Jakarta Validation provider đã được cấu hình toàn cục.
- `supports(Class<?>)` phải khớp class đang được binder validate. Đăng ký một validator không hỗ trợ target có thể gây lỗi cấu hình.
- `@Valid`/`@Validated` trên request argument làm Spring gọi validation trong các luồng phù hợp. Chỉ thêm validator trong `@InitBinder` không bảo đảm mọi object tự được validate nếu handler không có điểm kích hoạt.
- `errors.rejectValue(...)` thêm field error có mã riêng. Đây là **Spring Validator/Errors**, khác cách viết `jakarta.validation.ConstraintValidator`.
- Nếu muốn dùng cùng rule ở nhiều request DTO ngoài MVC, cân nhắc custom Jakarta constraint hoặc một validator/service dùng chung thay vì cài cứng controller-only binder.

## 9. Dự án Java 17 + Spring Boot chạy được

Ví dụ này làm rõ năm điều trong một ứng dụng:
1. `@InitBinder("profileForm")` chỉ chọn binder theo object name.
2. `setAllowedFields` không cho form tự set `admin` và ghi nhận trường bị suppressed.
3. `StringTrimmerEditor` và formatter LocalDate xử lý String của form.
4. Jakarta Validation (`@NotBlank`, `@Email`, `@NotNull`) kết hợp custom Spring Validator khi handler có `@Valid`.
5. `@RequestBody` JSON đi qua Jackson, **không** dùng setter-based WebDataBinder property-binding theo `allowedFields`; cùng controller còn có một form khác không nhận chính sách `profileForm`.

### 9.1. Cấu trúc thư mục

```text
init-binder-demo/
├── pom.xml
├── src/main/java/demo/binder/
│   ├── InitBinderApplication.java
│   ├── ProfileForm.java
│   ├── OtherForm.java
│   ├── ProfileFormValidator.java
│   └── ProfileController.java
└── src/test/java/demo/binder/
    └── ProfileControllerTest.java
```

### 9.2. `pom.xml`

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
    <artifactId>init-binder-demo</artifactId>
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

`spring-boot-starter-web` cung cấp Spring MVC Servlet và Jackson. `spring-boot-starter-validation` cung cấp Jakarta Validation provider. `spring-boot-starter-test` cung cấp JUnit Jupiter và MockMvc. Boot parent chọn phiên bản dependencies tương thích; đây là project minh họa dùng Boot 3.5.6, không tuyên bố đó là phiên bản Spring Boot mới nhất.

### 9.3. `InitBinderApplication.java`

```java
package demo.binder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InitBinderApplication {

    public static void main(String[] args) {
        SpringApplication.run(InitBinderApplication.class, args);
    }
}
```

### 9.4. `ProfileForm.java`

```java
package demo.binder;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.time.LocalDate;

public class ProfileForm {

    @NotBlank(message = "displayName.required")
    private String displayName;

    @NotBlank(message = "email.required")
    @Email(message = "email.invalid")
    private String email;

    @NotNull(message = "appointmentDate.required")
    private LocalDate appointmentDate;

    // Cố ý có setter admin để chứng minh allowlist chặn over-posting.
    private boolean admin;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public LocalDate getAppointmentDate() {
        return appointmentDate;
    }

    public void setAppointmentDate(LocalDate appointmentDate) {
        this.appointmentDate = appointmentDate;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

Ở code production, tốt nhất nên **loại hẳn `admin` khỏi request DTO**. Ở đây ta giữ nó chỉ để test việc binding suppression.

### 9.5. `OtherForm.java` — kiểm tra phạm vi annotation

```java
package demo.binder;

public class OtherForm {

    private String memo;
    private boolean admin;

    public String getMemo() {
        return memo;
    }

    public void setMemo(String memo) {
        this.memo = memo;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

`OtherForm` chỉ đóng vai trò **đối chứng**: vì tên model attribute khác `profileForm`, binder của nó không nhận allowlist riêng ở ví dụ. Đây không phải mẫu thiết kế phân quyền trong ứng dụng thực tế.

### 9.6. `ProfileFormValidator.java` — Spring Validator cục bộ

```java
package demo.binder;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class ProfileFormValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return ProfileForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        ProfileForm form = (ProfileForm) target;

        if ("blocked".equalsIgnoreCase(form.getDisplayName())) {
            errors.rejectValue(
                    "displayName",
                    "displayName.blocked",
                    "displayName is not allowed");
        }
    }
}
```

Rule này không gọi DB hay hệ thống bên ngoài, và `supports` đúng kiểu `ProfileForm`. Trong production, nếu rule phụ thuộc I/O hoặc quyền người dùng, thường nên đặt kiểm tra vào service layer thay vì binder validator.

### 9.7. `ProfileController.java` — phần chính của bài

```java
package demo.binder;

import jakarta.validation.Valid;
import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.format.Formatter;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Arrays;
import java.util.Locale;
import java.util.Map;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    @InitBinder("profileForm")
    void initProfileForm(WebDataBinder binder) {

        // Chỉ những fields này được setter-bind từ form.
        binder.setAllowedFields(
                "displayName", "email", "appointmentDate");

        // Chuẩn hóa tên, chỉ cho property displayName.
        binder.registerCustomEditor(
                String.class,
                "displayName",
                new StringTrimmerEditor(true));

        // Input form: 31/12/2026 -> LocalDate 2026-12-31.
        binder.addCustomFormatter(new Formatter<LocalDate>() {

            private final DateTimeFormatter pattern =
                    DateTimeFormatter.ofPattern("dd/MM/uuuu");

            @Override
            public LocalDate parse(String text, Locale locale) {
                return LocalDate.parse(text, pattern);
            }

            @Override
            public String print(LocalDate date, Locale locale) {
                return date.format(pattern);
            }
        }, "appointmentDate");

        // Bổ sung validator riêng, không thay global Bean Validation.
        binder.addValidators(new ProfileFormValidator());
    }

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> submitForm(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            var fields = errors.getFieldErrors().stream()
                    .map(error -> error.getField())
                    .distinct()
                    .sorted()
                    .toList();

            return ResponseEntity.badRequest().body(Map.of(
                    "status", "invalid",
                    "fields", fields,
                    "suppressed", Arrays.asList(
                            errors.getSuppressedFields())));
        }

        return ResponseEntity.ok(Map.of(
                "displayName", form.getDisplayName(),
                "email", form.getEmail(),
                "appointmentDate",
                form.getAppointmentDate().toString(),
                "admin", form.isAdmin(),
                "suppressed", Arrays.asList(
                        errors.getSuppressedFields())));
    }

    @PostMapping(
            path = "/other",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, Object> submitOther(
            @ModelAttribute("otherForm") OtherForm form) {

        return Map.of(
                "memo", form.getMemo(),
                "admin", form.isAdmin());
    }

    @PostMapping(
            path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> fromJson(
            @RequestBody ProfileForm form) {

        // JSON do Jackson giải mã; không phải setter binding
        // từ form parameters qua WebDataBinder.
        return Map.of(
                "displayName", form.getDisplayName(),
                "admin", form.isAdmin());
    }
}
```

Những điểm cần hiểu:

- `@InitBinder("profileForm")` chỉ đặt cấu hình khi binder có object name tương ứng.
- `@ModelAttribute("profileForm")` gắn tên rõ ràng; tránh phụ thuộc Spring suy ra tên.
- `setAllowedFields` áp vào **setter/property binding của form**. `admin=true` bị suppressed dù DTO có setter.
- `registerCustomEditor` chỉ tác động `displayName`; email không tự được trim theo ví dụ.
- `addCustomFormatter` cho `appointmentDate` chuyển `31/12/2026` sang `LocalDate.of(2026, 12, 31)`.
- `addValidators` thêm custom rule `"blocked"`. `@Valid` khiến Jakarta provider và Spring validators liên quan được áp dụng vào form.
- `BindingResult` nằm **ngay sau** `@ModelAttribute`; handler nhận được lỗi binding/validation để trả JSON có `fields` thay vì để framework tự ném `MethodArgumentNotValidException`.
- `errors.getSuppressedFields()` cho biết những property đã bị bỏ qua **vì chính sách binding**. Field suppressed **không mặc nhiên làm `errors.hasErrors()` thành true**; chính sách ứng dụng phải quyết định có từ chối request có field bị suppress hay chỉ bỏ qua và ghi nhận.
- Endpoint `/other` minh họa phạm vi object name: không có allowlist của `profileForm` ở `otherForm`. Việc một endpoint khác nhận `admin=true` trong demo này chỉ để quan sát scope, **không được dùng như một thiết kế quyền thực tế**.
- Endpoint `/json` không đặt `@Valid` nên không kích hoạt validation DTO ở đó. Nó minh họa Jackson vẫn đọc `admin=true` và giữ `displayName` có khoảng trắng; `@InitBinder` không phải giải pháp chặn JSON property assignment.

### 9.8. `ProfileControllerTest.java` — kiểm thử bằng MockMvc

```java
package demo.binder;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void allowedFieldsTrimDateAndSuppressAdmin() throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "  Linh  ")
                        .param("email", "linh@example.com")
                        .param("appointmentDate", "31/12/2026")
                        .param("admin", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Linh"))
                .andExpect(jsonPath("$.appointmentDate")
                        .value("2026-12-31"))
                .andExpect(jsonPath("$.admin").value(false))
                .andExpect(jsonPath("$.suppressed[0]")
                        .value("admin"));
    }

    @Test
    void blankDisplayNameIsRejectedByBeanValidation()
            throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "   ")
                        .param("email", "linh@example.com")
                        .param("appointmentDate", "31/12/2026"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("invalid"))
                .andExpect(jsonPath("$.fields[0]")
                        .value("displayName"));
    }

    @Test
    void customValidatorRejectsBlockedName() throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "blocked")
                        .param("email", "linh@example.com")
                        .param("appointmentDate", "31/12/2026"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0]")
                        .value("displayName"));
    }

    @Test
    void invalidDateIsBindingError() throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Linh")
                        .param("email", "linh@example.com")
                        .param("appointmentDate", "31/99/2026"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0]")
                        .value("appointmentDate"));
    }

    @Test
    void invalidEmailIsBeanValidationError() throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Linh")
                        .param("email", "not-an-email")
                        .param("appointmentDate", "31/12/2026"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0]")
                        .value("email"));
    }

    @Test
    void missingDateFailsNotNull() throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Linh")
                        .param("email", "linh@example.com"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0]")
                        .value("appointmentDate"));
    }

    @Test
    void otherFormDoesNotInheritProfileFormAllowlist()
            throws Exception {
        mvc.perform(post("/profiles/other")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("memo", "hello")
                        .param("admin", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.memo").value("hello"))
                .andExpect(jsonPath("$.admin").value(true));
    }

    @Test
    void jsonUsesJacksonNotFormPropertyBinding() throws Exception {
        mvc.perform(post("/profiles/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "displayName": "  Linh  ",
                                  "email": "linh@example.com",
                                  "appointmentDate": "2026-12-31",
                                  "admin": true
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName")
                        .value("  Linh  "))
                .andExpect(jsonPath("$.admin").value(true));
    }

    @Test
    void isoDateIsNotTheFormFormatterPattern()
            throws Exception {
        mvc.perform(post("/profiles/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "Linh")
                        .param("email", "linh@example.com")
                        .param("appointmentDate", "2026-12-31"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0]")
                        .value("appointmentDate"));
    }
}
```

Chạy tại thư mục `init-binder-demo`, với JDK 17+ và Maven có thể tải dependencies:

```bash
mvn test
```

**Kỳ vọng 9 test đều pass.** Vì `MockMvc` không cần mở cổng HTTP, test trực tiếp đi qua Spring MVC argument resolution/binding/validation và kiểm tra status/JSON. Không nên coi test gọi thẳng `new ProfileController().submitForm(...)` là kiểm thử `@InitBinder`: lời gọi Java thuần không chạy `DispatcherServlet` hay binder factory.

### 9.9. Vì sao các test chứng minh điều quan trọng?

| Test | Điều được chứng minh |
| --- | --- |
| `allowedFieldsTrimDateAndSuppressAdmin` | Allowlist, editor, formatter cùng hoạt động; admin bị suppressed nhưng response vẫn 200 vì không có lỗi validation |
| `blankDisplayNameIsRejectedByBeanValidation` | Trim thành null và `@NotBlank` bắt lỗi qua `@Valid` |
| `customValidatorRejectsBlockedName` | Spring Validator được thêm bởi `@InitBinder` có thể sinh `FieldError` |
| `invalidDateIsBindingError` | Chuỗi ngày sai không đổi được thành LocalDate; BindingResult ghi type mismatch |
| `invalidEmailIsBeanValidationError` | Jakarta `@Email` được provider kiểm tra |
| `missingDateFailsNotNull` | Không có input ngày dẫn đến property null và vi phạm `@NotNull` |
| `otherFormDoesNotInheritProfileFormAllowlist` | `@InitBinder("profileForm")` không áp lên object name `otherForm` |
| `jsonUsesJacksonNotFormPropertyBinding` | `@RequestBody` JSON không được bảo vệ bởi form-property allowlist/editor |
| `isoDateIsNotTheFormFormatterPattern` | Formatter cục bộ đang yêu cầu `dd/MM/uuuu` thay vì ISO |

Kết quả lỗi JSON ở demo do **chính controller xây dựng** bằng `ResponseEntity`; Spring không mặc định mọi ứng dụng trả trường `"fields"` hay `"suppressed"`. Trong ứng dụng thật, hãy dùng error schema thống nhất và chỉ công bố các thông tin cần thiết.

## 10. Chạy thử bằng curl

Khởi động:

```bash
mvn spring-boot:run
```

### 10.1. Form hợp lệ với field không được phép

```bash
curl -i -X POST \
  http://localhost:8080/profiles/form \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=  Linh  ' \
  --data-urlencode 'email=linh@example.com' \
  --data-urlencode 'appointmentDate=31/12/2026' \
  --data-urlencode 'admin=true'
```

Dự kiến HTTP **200**, body có các giá trị quan trọng:

```json
{
  "displayName": "Linh",
  "email": "linh@example.com",
  "appointmentDate": "2026-12-31",
  "admin": false,
  "suppressed": ["admin"]
}
```

Không bắt buộc JSON properties được in đúng thứ tự ở ví dụ trên. `admin` vẫn false dù form gửi true vì `setAllowedFields` không cho phép bind property đó.

### 10.2. Form lỗi do validator

```bash
curl -i -X POST \
  http://localhost:8080/profiles/form \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=blocked' \
  --data-urlencode 'email=linh@example.com' \
  --data-urlencode 'appointmentDate=31/12/2026'
```

Dự kiến HTTP **400**, body mô tả:

```json
{
  "status": "invalid",
  "fields": ["displayName"],
  "suppressed": []
}
```

Đây là lỗi **custom Spring Validator**, không phải conversion error. Đổi input `appointmentDate` thành `31/99/2026` sẽ tạo binding error ở field ngày.

### 10.3. JSON với cùng tên field

```bash
curl -i -X POST \
  http://localhost:8080/profiles/json \
  -H 'Content-Type: application/json' \
  -d '{"displayName":"  Linh  ","email":"linh@example.com","appointmentDate":"2026-12-31","admin":true}'
```

Dự kiến HTTP **200**; kết quả có `displayName` giữ dấu cách và `admin=true`. Jackson đọc JSON và gọi setters/constructor theo cơ chế của message converter, không thực thi **form property-binding whitelist** của `WebDataBinder`.

**Ý nghĩa bảo mật:** Nếu client không được phép set `admin`, bạn phải ngăn ở **JSON DTO/API contract/authorization** nữa. `@InitBinder` không phải cơ chế chung kiểm soát mọi cách deserialization dữ liệu vào Java.

## 11. Phân biệt `@ModelAttribute` với `@RequestBody`

### 11.1. `@ModelAttribute`: vùng hoạt động chính của binder

`@ModelAttribute` thường được dùng cho query/form fields (và các dữ liệu request có thể bind thành properties). Spring tạo/chuẩn bị command object, bind các giá trị theo tên field và có thể validate.

```java
@PostMapping("/form")
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {
    // ...
}
```

Khi đó `@InitBinder("profileForm")` được dùng để cấu hình binder tương ứng. `setAllowedFields`, `StringTrimmerEditor`, `Formatter` và `addValidators` có thể tác động đúng những pha được binder đảm nhiệm.

### 11.2. `@RequestBody`: `HttpMessageConverter` (thường Jackson)

```java
@PostMapping("/json")
public ResponseEntity<?> submit(
        @Valid @RequestBody ProfileDto body) {
    // ...
}
```

Với `Content-Type: application/json`, Spring dùng `HttpMessageConverter` để deserialize body thành object. Jackson quyết định cách ánh xạ JSON fields/constructors/setters. `WebDataBinder#setAllowedFields` **không chặn Jackson** gán field, và custom `PropertyEditor`/`Formatter` dùng cho form binding không tự thay parser JSON.

**Sắc thái quan trọng:** Spring MVC **có thể vẫn tạo WebDataBinder cho bước validation** của `@RequestBody` khi argument đã được message converter tạo. Vì vậy không nên tuyên bố “`@InitBinder` không bao giờ được gọi với `@RequestBody`”. Khẳng định đúng là: **cấu hình property binding trong `@InitBinder` không thay cơ chế JSON deserialization của Jackson**. Những validators được thêm vào binder có thể tham gia khi request argument được validate theo cấu hình và object name tương ứng.

Nếu muốn cấm một JSON property:
- Dùng DTO input riêng không chứa property đó.
- Cân nhắc chính sách Jackson như `@JsonIgnore` / cấu hình deserialization khi phù hợp.
- Áp authorization/business rules ở service.
- Không dựa riêng vào `WebDataBinder#setAllowedFields`.

### 11.3. `@RequestParam` và conversion simple values

`@RequestParam("count") int count` cũng đòi type conversion từ chuỗi của HTTP. Cơ chế conversion/binder của Spring MVC có thể hỗ trợ tùy biến ở những argument resolver tương ứng. Tuy nhiên `@InitBinder("profileForm")` của một form **không** nên được coi là format rule áp cho mọi scalar parameter: object name/đường resolution có thể khác.

Nếu cần quy tắc parse cho một type trên toàn ứng dụng, `WebMvcConfigurer#addFormatters`/`FormattingConversionService` thường rõ ràng hơn.

## 12. `BindingResult`: ba loại vấn đề dễ bị gộp

Một `BindingResult` có thể cho thấy các tình huống khác nhau:

| Hiện tượng | Ý nghĩa | Có mặc định `hasErrors()`? |
| --- | --- | --- |
| Client gửi chuỗi `"31/99/2026"` cho `LocalDate` | Lỗi conversion/type mismatch | Thường **có** |
| `@NotBlank` phát hiện displayName rỗng | Jakarta Bean Validation thất bại | **Có** khi validation đã kích hoạt |
| Custom `ProfileFormValidator` rejectValue | Spring Validator thất bại | **Có** |
| Client gửi `admin=true` nhưng field không trong allowlist | Field bị suppressed khỏi property binding | Không nhất thiết |
| Client gửi extra field không tồn tại trên DTO | Unknown field có thể được bỏ qua hoặc báo lỗi tùy config | Không phải luôn là validation error |
| Binder `setRequiredFields(...)` phát hiện một field thiếu | Binding required-field error | Có thể có |

Khi muốn **từ chối request có field suppressed**, bạn có thể tự đặt chính sách:

```java
if (errors.getSuppressedFields().length > 0) {
    return ResponseEntity.badRequest().body(
            Map.of("error", "unexpected.fields"));
}
```

Đoạn này là **biến thể minh họa**. Không thêm nguyên xi vào `submitForm()` trong project phần 9 nếu muốn giữ test `allowedFieldsTrimDateAndSuppressAdmin` nhận HTTP 200. Trong thực tế, việc trả 400 khi có suppressed fields thường là một lựa chọn phòng vệ hợp lý khi API chỉ cho phép một tập field rất rõ.

### 12.1. Đọc field errors

```java
for (var error : errors.getFieldErrors()) {
    String field = error.getField();
    String code = error.getCode();
    String message = error.getDefaultMessage();
}
```

Bạn có thể chuyển chúng thành một danh sách lỗi có cấu trúc:
- `field`: tên property.
- `code`: ví dụ `NotBlank`, `typeMismatch` hoặc mã tự định nghĩa.
- `message`: bản thông báo sau interpolation/localization.

Đừng trực tiếp trả `getRejectedValue()` cho client nếu dữ liệu có thể nhạy cảm, và đừng coi error message là ID ổn định cho frontend. Phản hồi API nên có error code rõ ràng.

### 12.2. Vị trí `BindingResult` là một phần chữ ký handler

Đúng:

```java
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors) {
    // ...
}
```

Không đúng nếu hy vọng bắt lỗi của form:

```java
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        @RequestParam String mode,
        BindingResult errors) {
    // BindingResult không còn ngay sau form.
}
```

`BindingResult`/`Errors` thường phải đứng **ngay sau** argument được bind/validate mà nó mô tả. Nếu bạn không cung cấp `BindingResult` đúng chỗ và form invalid, Spring MVC có thể ném `MethodArgumentNotValidException`; với direct constraints trên method, loại exception có thể là `HandlerMethodValidationException` tùy chữ ký.

## 13. Validator cục bộ không giống `@Validated` qua AOP

Có ba việc tách biệt:

| Cơ chế | Khi nào chạy? | Đối tượng liên quan |
| --- | --- | --- |
| `@InitBinder` và `binder.addValidators(...)` | Khi MVC chuẩn bị binder, validator chạy nếu bước validation phù hợp được kích hoạt | Command object / request argument |
| `@Valid @ModelAttribute` | Khi MVC bind và validate request object | DTO fields, custom validators |
| `@Service @Validated` qua `MethodValidationPostProcessor` | Khi method invocation đi qua Spring AOP proxy | Method parameter / return value |

Gắn `@Validated` trên một service **không thay thế** việc cấu hình `@InitBinder` của controller. Ngược lại, `@InitBinder` không phải AOP advisor, không tự intercept method calls bên ngoài Spring MVC.

Ở controller Spring Framework 6.1+, direct constraints trên handler method parameters còn có thể kích hoạt built-in **method validation**, tạo `HandlerMethodValidationException`. `@Valid` trên một DTO argument đơn lẻ không tự nó là một direct constraint. Nếu bạn chỉ cần groups cho form, dùng `@Validated(Group.class) @ModelAttribute(...)` ở argument thích hợp; không cần đặt class-level `@Validated` lên toàn controller chỉ để chọn group.

## 14. Một số API khác của `WebDataBinder` và tác động

### 14.1. `setRequiredFields`

```java
@InitBinder("profileForm")
void init(WebDataBinder binder) {
    binder.setRequiredFields("displayName", "email");
}
```

Các field được khai báo là **required at binding level**. Điều này có thể tạo binding errors cho field không có mặt. Không đồng nhất nó với `@NotBlank`:
- `setRequiredFields` liên quan tới presence trong dữ liệu binding.
- `@NotBlank` kiểm tra giá trị String sau binding/normalization và cũng không chấp nhận toàn whitespace.
- Hợp đồng nghiệp vụ có thể cần cả hai, nhưng nhiều dự án chọn Bean Validation vì dễ dùng lại và diễn đạt rõ.

Đoạn này là minh họa riêng; project chính ở phần 9 **không** dùng `setRequiredFields` để người học quan sát rõ `@NotNull`/`@NotBlank`.

### 14.2. `setAutoGrowNestedPaths` và collection limits

```java
binder.setAutoGrowNestedPaths(false);
binder.setAutoGrowCollectionLimit(128);
```

Các API này kiểm soát khả năng binder tự mở rộng object graph hoặc collection khi property path dạng `addresses[100]` được bind. Giới hạn phù hợp giúp tránh request cố tình tạo graph/collection rất lớn. Nhưng thay đổi mặc định có thể gây lỗi binding cho form hợp lệ dùng nested paths, nên phải test và xem tài liệu phiên bản cụ thể.

Không coi collection limit là biện pháp bảo mật đầy đủ: vẫn cần HTTP request size limits, max number of parameters, DTO design và authorization.

### 14.3. `setIgnoreUnknownFields` và `setIgnoreInvalidFields`

```java
binder.setIgnoreUnknownFields(false);
binder.setIgnoreInvalidFields(false);
```

Hai cơ chế liên quan tới:
- Field **không tồn tại** trong object.
- Field path tồn tại về mặt tên nhưng không thể truy cập/khởi tạo target nested path.

Chúng không thay thế `setAllowedFields`. Một field bị **suppressed vì policy** không giống một unknown field; các lỗi suppressed được theo dõi qua `BindingResult.getSuppressedFields()`. Chỉ thay những flags này nếu hiểu rõ tác động trên form, nested properties và exception/error handling.

### 14.4. `setValidator`, `addValidators`, `replaceValidators`

`setValidator(...)` hoặc `replaceValidators(...)` có thể thay cấu hình validator tùy overload/version; `addValidators(...)` chỉ **thêm** validator. Với controller cần mở rộng quy tắc, `addValidators` thường giữ được Jakarta provider của Spring Boot nếu provider đã được đăng ký mặc định. Không tùy tiện `replaceValidators` hoặc loại bỏ global Bean Validation khi dự án cần `@NotBlank`, `@Email`, `@Valid`.

Khi thêm custom validator, hãy kiểm tra `supports()` và test rằng **cả custom lẫn Jakarta constraints** đều thực thi trên object cần dùng.

## 15. Những lỗi phổ biến khi dùng `@InitBinder`

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Cho rằng `@InitBinder` là endpoint | Không nhận request ở method đó | Endpoint phải dùng `@GetMapping`/`@PostMapping`... |
| Dùng `@InitBinder("user")` nhưng `@ModelAttribute("profileForm")` | Cấu hình không áp vào binder mong muốn | Khớp object name chính xác |
| Đặt `@InitBinder` không giới hạn cho controller có nhiều form | Allowlist hoặc formatter có thể ảnh hưởng DTO khác | Giới hạn theo object name |
| Bind trực tiếp JPA entity từ form | Dễ over-posting thuộc tính nhạy cảm | Dùng request DTO chuyên biệt và allowlist |
| Chỉ dùng `setDisallowedFields("admin")` | Quên field mới hoặc biến thể tên | Ưu tiên explicit `setAllowedFields` |
| Nghĩ `setAllowedFields` chặn cả JSON Jackson | JSON message converter không dùng setter property binder | DTO/Jackson config/authorization riêng |
| Cho rằng suppressed field tự sinh 400 | Suppression không nhất thiết là binding error | Xem `getSuppressedFields()` và quyết định policy |
| Đăng ký `StringTrimmerEditor` rộng quá | Có thể thay giá trị password/token/email không mong muốn | Cấu hình theo field phù hợp |
| Đặt Formatter xử lý LocalDate nhưng request là JSON | Jackson không dùng formatter form của binder | Dùng Jackson date format hoặc DTO riêng |
| Thêm custom validator nhưng quên `@Valid`/`@Validated` | Có thể không kích hoạt validate | Đặt annotation tại request argument |
| `supports()` trả false cho DTO | Validator không hợp kiểu, có thể lỗi lúc cấu hình | Test target type chính xác |
| Dùng `@NotBlank` trên LocalDate hoặc int | Kiểu constraint không tương thích | Dùng `@NotNull`, `@Min`, `@Future`... |
| Đặt `BindingResult` không ngay sau form | Handler không nhận binding errors đúng cách | Đặt liền sau `@ModelAttribute` |
| Dùng editor chứa state static mutable | Có thể gây lỗi concurrent requests | Mỗi binder/formatter nên stateless hoặc thread-safe |
| Bật `setDeclarativeBinding(true)` nhưng mong setter-bind mọi field | Property binding bị giới hạn nếu không allowlist | Thiết kế constructor binding hoặc explicit allowedFields |
| Cho rằng allowlist bảo vệ cả constructor binding | Hai kênh binding khác nhau | Thiết kế constructor DTO đúng public fields |
| Dựa vào `@InitBinder` để authorize việc đổi admin/role | Binder chỉ là lớp chặn input, không phải authorization | Kiểm tra quyền ở service/security |

## 16. Debug một form không bind hoặc validate như dự kiến

Trình tự điều tra có thể dùng trong integration test:

1. **Xác nhận đúng stack:** Có dùng Spring MVC Servlet hay WebFlux?
2. **Xác nhận handler được chọn:** URL, HTTP method và Content-Type có đúng không?
3. **Xác nhận argument annotation:** Có `@ModelAttribute("profileForm")` hoặc request argument được binder xử lý không?
4. **Xác nhận object name:** `@InitBinder("profileForm")` khớp tên `@ModelAttribute` chưa? Một ký tự khác cũng không khớp.
5. **Xác nhận form field names:** `displayName` trong HTML có đúng setter `setDisplayName` không?
6. **Xác nhận allowlist:** Field có bị `setAllowedFields` suppress không? Kiểm tra `BindingResult.getSuppressedFields()`.
7. **Xác nhận editor/formatter:** Format `dd/MM/uuuu` có khớp request không? Có annotation format khác đang chi phối?
8. **Xác nhận validators:** Có Jakarta provider và `@Valid`/`@Validated`? Custom `supports()` có khớp?
9. **Xác nhận BindingResult:** Có đứng ngay sau argument cần validate? Có bind error và field errors nào?
10. **Xác nhận conversion exception:** `typeMismatch` khác `NotBlank`; đừng gộp mọi 400 thành một nguyên nhân.
11. **Kiểm tra body format:** JSON đi qua Jackson, không phải form property binding.
12. **Kiểm tra advice chung:** Có `@ControllerAdvice` nào sửa binder trên tất cả controllers?
13. **Kiểm tra DTO design:** Constructor binding có đang nhận field mà setter allowlist không kiểm soát?
14. **Kiểm tra security:** Có client cố truyền field quyền/admin/ID mà controller không nên tin?
15. **Kiểm tra test path:** `MockMvc` đi qua framework, khác việc tự gọi handler method bằng Java.

Đặc biệt, với một request thành công, bạn vẫn nên kiểm tra xem những field không hợp lệ đã bị bỏ qua hay chưa — HTTP 200 không chứng minh mọi input field đã được dùng.

## 17. Bài tập thực hành

1. Đổi `@InitBinder("profileForm")` thành `@InitBinder("otherForm")`. Dự đoán test nào thất bại: trim, ngày, allowlist, custom validator và scope.
2. Bỏ `setAllowedFields`, gửi `admin=true` đến `/profiles/form`. Quan sát response để giải thích nguy cơ over-posting.
3. Giữ allowlist nhưng thêm `unknownFlag=true`. Dùng `getSuppressedFields()` xem trường nào bị chặn, khác gì một unknown field.
4. Đổi `StringTrimmerEditor(true)` thành `StringTrimmerEditor(false)` rồi gửi `displayName="  "`. Vì sao `@NotBlank` vẫn từ chối, còn giá trị trong DTO khác?
5. Đổi pattern sang `yyyy-MM-dd`, chạy lại test ngày; giải thích vì sao `31/12/2026` không còn được chấp nhận.
6. Tạm bỏ `@Valid` trên `@ModelAttribute("profileForm")` và gửi `displayName=blocked`. Kiểm tra custom validator có còn tự chạy hay không.
7. Tạm đổi `ProfileFormValidator.supports` thành hỗ trợ class khác. Quan sát tác động đăng ký validator và lý do phải implement đúng contract.
8. Đổi policy: trả HTTP 400 nếu `getSuppressedFields().length > 0`; cập nhật test để kỳ vọng status và error code mới.
9. Viết một DTO immutable record chỉ cho phép `displayName` và `email`. Bật `setDeclarativeBinding(true)`; so sánh với setter binding của DTO mutable.
10. Chuyển `@InitBinder` sang `@ControllerAdvice(assignableTypes=ProfileController.class)` rồi chạy lại test; xem phạm vi áp dụng.
11. Gắn `@DateTimeFormat(pattern="dd/MM/uuuu")` lên field, bỏ custom formatter trong binder, xác nhận kết quả conversion còn đúng.
12. Thêm endpoint JSON có `@Valid @RequestBody ProfileForm`; xem validation có chạy nhưng allowlist không chặn Jackson như thế nào.
13. Đăng ký formatter toàn cục qua `WebMvcConfigurer#addFormatters`, rồi loại formatter tại controller; phân tích trade-off.
14. Thêm nested field `contact.email` và thiết kế allowlist hẹp để client chỉ sửa email, không sửa các thuộc tính khác của `contact`.

**Tóm tắt cần nhớ:** `@InitBinder` là một **hook cấu hình `WebDataBinder`** theo phạm vi controller hoặc object name, giúp kiểm soát cách form/query dữ liệu được bind, chuyển kiểu và validate. Nó không thay thế `@Valid`, `BindingResult`, Jackson JSON deserialization, DTO design hay authorization. Trước khi dùng `@InitBinder`, hãy xác định rõ **đối tượng nào đang được bind**, **kênh binding nào** đang chạy và **những field nào** được phép nhận từ client.

## 18. Nguồn tài liệu chính thức

- [Spring Framework 6.2 — @InitBinder trong Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — @ModelAttribute argument binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @RequestBody và HttpMessageConverter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — Validation config và custom @InitBinder Validator](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — WebDataBinder API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/WebDataBinder.html)
- [Spring Framework 6.2 — Spring MVC validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — @ControllerAdvice scope](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html)
- [Spring Boot 3.5 — Testing MVC with MockMvc](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Jakarta Validation 3.0 specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
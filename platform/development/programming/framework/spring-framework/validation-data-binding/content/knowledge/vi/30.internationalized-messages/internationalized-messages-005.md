# Resource bundle và quy ước tệp thông báo trong Spring Framework

## Mục tiêu

**Thông báo đa ngữ** trong một ứng dụng Java/Spring nên được quản lý bằng **message code** ổn định và các **resource bundle** thay vì viết cố định câu chữ trong controller, template hoặc service. Với một code `signup.title`, hệ thống có thể trả `Đăng ký` cho tiếng Việt, `Sign up` cho tiếng Anh và một câu mặc định khi locale yêu cầu chưa có bản dịch.

Sau bài này, bạn sẽ biết:

- Cách đặt tên tệp `messages.properties`, `messages_en.properties`, `messages_vi.properties`, `messages_vi_VN.properties`.
- Vai trò của basename, locale, file gốc, fallback và charset UTF-8.
- Cách cấu hình `spring.messages.basename` và các thuộc tính `spring.messages.*` trong Spring Boot.
- Cách gọi `MessageSource.getMessage(...)`, truyền arguments và xử lý `NoSuchMessageException`.
- Sự khác biệt giữa Spring `messages*.properties` và Jakarta Bean Validation `ValidationMessages*.properties`.
- Cách hiển thị lỗi `BindingResult`, `FieldError` với Thymeleaf theo locale của request.
- Cách kiểm tra ứng dụng Java 17+ / Spring Boot 3.5.7 bằng MockMvc và `Accept-Language`.

## 1. Resource bundle, message code và Locale

**Message code** là khóa logic, không phải nguyên câu hiển thị:

~~~properties
signup.title=Sign up
signup.submit=Submit
signup.welcome=Hello {0}!
~~~

Đặt mã theo namespace giúp tránh trùng tên:

~~~text
common.action.save
common.action.cancel
signup.title
signup.name
signup.validation.age
checkout.payment.failed
orders.delivery.estimated
~~~

Đây là quy ước do ứng dụng tự đặt, không phải cú pháp bắt buộc của Java. Nên giữ key ổn định khi biên dịch viên chỉnh nội dung, không đặt các tên mơ hồ như `message1` hoặc `error` trong dự án lớn.

**Resource bundle** là tập bản dịch của các key theo `Locale`. Trong Maven:

~~~text
src/main/resources/
├── messages.properties
├── messages_en.properties
├── messages_vi.properties
└── messages_vi_VN.properties
~~~

- `messages` là **basename**.
- `messages.properties` là file gốc không gắn locale.
- `messages_en.properties` dùng cho tiếng Anh.
- `messages_vi.properties` dùng cho tiếng Việt nói chung.
- `messages_vi_VN.properties` có nội dung chỉ áp dụng khi locale là tiếng Việt tại Việt Nam.

Ngôn ngữ/vùng khi trao đổi qua HTTP thường viết `vi-VN`. Trong tên file Java `ResourceBundle`, dạng phổ biến là `vi_VN` với dấu gạch dưới; không tự đổi thành `messages_vi-VN.properties`.

Ví dụ tạo Locale:

~~~java
Locale vi = Locale.forLanguageTag("vi");
Locale viVN = Locale.forLanguageTag("vi-VN");
Locale enUS = Locale.forLanguageTag("en-US");
~~~

Cần import `java.util.Locale`. `Locale` không chứa bản dịch của ứng dụng: đó là dữ liệu đầu vào để `MessageSource` chọn bundle. Locale còn ảnh hưởng cách format ngày, số và tiền, nhưng dịch resource bundle không tự động cấu hình mọi kiểu dữ liệu.

## 2. File gốc và Spring Boot auto-configuration

Spring Boot 3.5 mặc định tìm basename `messages` ở gốc classpath. Với cấu trúc Maven, file gốc cần ở:

~~~text
src/main/resources/messages.properties
~~~

**Điểm dễ quên:** tài liệu Spring Boot yêu cầu có **file properties mặc định** phù hợp với basename để tự cấu hình `MessageSource`. Nếu chỉ tạo `messages_vi.properties`, `messages_en.properties` mà bỏ `messages.properties` thì không nên giả định Boot sẽ phát hiện và auto-configure đúng MessageSource.

File gốc cũng đóng vai trò fallback khi một key chưa có bản dịch theo locale. Có thể dùng tiếng Anh làm ngôn ngữ fallback như trong demo, nhưng ngôn ngữ gốc là quyết định sản phẩm.

### Đổi basename

Muốn lưu file trong thư mục riêng:

~~~text
src/main/resources/i18n/ui.properties
src/main/resources/i18n/ui_vi.properties
src/main/resources/i18n/ui_en.properties
~~~

cấu hình:

~~~properties
spring.messages.basename=i18n/ui
~~~

Không thêm hậu tố `.properties`, `_vi` hoặc toàn bộ đường dẫn `src/main/resources` vào giá trị basename.

Có thể khai báo nhiều basenames:

~~~text
src/main/resources/messages.properties
src/main/resources/messages_vi.properties
src/main/resources/i18n/errors.properties
src/main/resources/i18n/errors_vi.properties
~~~

~~~properties
spring.messages.basename=messages,i18n/errors
~~~

Khi nhiều bundle có cùng key, thứ tự ưu tiên phụ thuộc MessageSource và cấu hình basenames. Đừng dựa vào collision ngẫu nhiên; đặt namespace theo feature và viết test nếu cần override một cách có chủ đích.

### Phân biệt cấu hình và dữ liệu dịch

~~~properties
# application.properties - cấu hình
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

~~~properties
# messages.properties - dữ liệu
signup.title=Sign up
signup.submit=Submit
~~~

Đặt `signup.title` trong `application.properties` không khiến nó tự trở thành bản dịch của Spring MessageSource. Hai tệp có mục đích khác nhau.

## 3. Locale fallback và thứ tự tìm file

Giả sử:

~~~properties
# messages.properties
signup.title=Sign up
signup.region=General message
~~~

~~~properties
# messages_vi.properties
signup.title=Đăng ký
signup.region=Thông điệp chung cho tiếng Việt
~~~

~~~properties
# messages_vi_VN.properties
signup.region=Thông điệp riêng cho Việt Nam
~~~

Tra `signup.region` với locale `vi-VN` sẽ ưu tiên bản dịch chuyên biệt rồi lần lượt rơi về bản tổng quát:

~~~text
messages_vi_VN.properties
     ↓ không có key?
messages_vi.properties
     ↓ không có key?
messages.properties
     ↓ không có key?
default message / NoSuchMessageException
~~~

| Locale | Key | Kết quả |
| --- | --- | --- |
| `vi-VN` | `signup.region` | Thông điệp riêng cho Việt Nam |
| `vi` | `signup.region` | Thông điệp chung cho tiếng Việt |
| `vi-VN` | `signup.title` | Đăng ký |
| `en-US` | `signup.title` | Sign up, nếu en không override |
| `fr-FR` | `signup.title` | Sign up, theo fallback trong demo |

**Fallback theo language/country khác fallback sang locale của máy chủ.** Một số implementation có thể thử JVM default locale khi không có biến thể phù hợp, khiến cùng request `fr-FR` trên máy có locale tiếng Việt hoặc tiếng Anh trả nội dung khác nhau.

Để test và vận hành nhất quán:

~~~properties
spring.messages.fallback-to-system-locale=false
~~~

Khi đó ứng dụng ưu tiên bundle của locale yêu cầu, rồi tệp gốc, không tùy thuộc locale của hệ điều hành. Nếu nghiệp vụ cố tình dùng system locale, cần ghi rõ policy và test tương ứng.

Không cần tạo tệp `messages_en_GB.properties` cho mọi quốc gia: chỉ tạo khi có khác biệt thật sự. Với locale chứa script/variant phức tạp, quy tắc tìm candidate bundles của Java còn nhiều nhánh; nên kiểm tra bằng unit tests thay vì tự ghép tên file.

## 4. API MessageSource

`org.springframework.context.MessageSource` có các overload quan trọng.

### Có fallback do caller chỉ định

~~~java
String text = messageSource.getMessage(
        "signup.title",
        null,
        "Registration",
        Locale.forLanguageTag("vi"));
~~~

Nếu tìm thấy `signup.title` trong bundle tiếng Việt, trả `Đăng ký`. Nếu không tìm thấy key ở các file phù hợp, trả `Registration`.

### Không có fallback

~~~java
String text = messageSource.getMessage(
        "signup.title",
        null,
        Locale.ENGLISH);
~~~

Nếu không tìm thấy key, overload này ném `NoSuchMessageException`. **Không có file cho locale** không có nghĩa lỗi: key vẫn có thể đến từ `messages.properties`.

### MessageSourceResolvable

~~~java
MessageSourceResolvable resolvable =
        new DefaultMessageSourceResolvable(
                new String[] {
                    "signup.title", "common.title"
                },
                null,
                "Sign up");

String text = messageSource.getMessage(
        resolvable, Locale.ENGLISH);
~~~

Snippet cần import `MessageSourceResolvable` và `DefaultMessageSourceResolvable` từ Spring. Một resolvable chứa nhiều codes theo thứ tự ưu tiên, arguments và default message. `FieldError`/`ObjectError` trong Spring Validation cũng cung cấp cơ chế như vậy.

Không lưu câu dịch vào biến static trong lúc khởi động nếu server cần phục vụ đồng thời nhiều locale. Hãy resolve tại request boundary hoặc truyền Locale tường minh từ caller.

## 5. Thông điệp có tham số và MessageFormat

Một message có thể nhận dữ liệu:

~~~properties
signup.welcome=Hello {0}!
orders.summary=Order {0} contains {1,number} items.
~~~

~~~java
String message = messageSource.getMessage(
        "signup.welcome",
        new Object[] {"Lan"},
        Locale.ENGLISH);
~~~

Kết quả:

~~~text
Hello Lan!
~~~

`{0}` là argument đầu tiên, `{1}` là argument thứ hai. Các biểu thức `{0,number}`, `{1,date,short}` sử dụng quy tắc `java.text.MessageFormat` với Locale phù hợp. Truyền kiểu giá trị thích hợp; `LocalDate` Java Time không mặc nhiên là `java.util.Date` trong mọi API MessageFormat.

### Dấu nháy đơn

MessageFormat dùng dấu `'` để quote. Muốn hiện một dấu nháy đơn trong message có tham số thường phải dùng hai dấu:

~~~properties
orders.ready=You''ve got {0} orders.
~~~

Với argument 2, kết quả:

~~~text
You've got 2 orders.
~~~

Khi muốn in literal `{0}` thay vì thay argument, phải tuân thủ quoting/escaping của MessageFormat. Đừng dùng cú pháp thay biến của JavaScript hoặc Thymeleaf trong `.properties` rồi kỳ vọng chúng được MessageFormat xử lý.

Spring Boot có:

~~~properties
spring.messages.always-use-message-format=false
~~~

Khi để mặc định, Spring có thể tối ưu câu không cần arguments. Nếu bật `true`, cả câu tĩnh cũng đi qua MessageFormat và cách escape apostrophe có thể khác. Hãy kiểm thử những câu chứa `'` hoặc braces khi thay cấu hình.

## 6. Encoding tiếng Việt

Spring Boot 3.5 có thể dùng UTF-8 cho các message bundles; đặt rõ:

~~~properties
spring.messages.encoding=UTF-8
~~~

Tệp UTF-8 có thể chứa trực tiếp:

~~~properties
signup.title=Đăng ký
signup.name=Họ và tên
signup.success=Đã tiếp nhận
~~~

Một số dự án cũ dùng Unicode escape như `\u0110\u0103ng k\u00fd`; với UTF-8 được cấu hình đúng, bạn không cần biến mọi câu dịch thành dạng escape khó đọc.

File `.properties` nhận dấu `=` hoặc `:` phân tách key/value; dấu `#`/`!` mở đầu comment; ký tự backslash được dùng cho escape và line continuation. Kiểm tra encoding giữa editor, Git, Maven và runtime; không mặc định thư viện đọc properties bên ngoài Spring đều đọc theo `spring.messages.encoding`.

## 7. Spring messages và Jakarta ValidationMessages là hai convention

Đây là điểm quan trọng của chủ đề **validation-data-binding**.

### 7.1. Mã lỗi của Spring BindingResult

Giả sử DTO:

~~~java
public class SignupForm {
    @NotBlank
    private String name;
}
~~~

Nếu `name=""`, Spring tạo `FieldError` và các message codes có mức độ cụ thể khác nhau, ví dụ:

~~~text
NotBlank.signupForm.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
~~~

Đặt trong Spring message bundle:

~~~properties
# messages_vi.properties
NotBlank.signupForm.name=Tên không được để trống
~~~

Thymeleaf `th:errors="*{name}"` có thể resolve `FieldError` qua MessageSource theo locale vi. Mã theo object/field cụ thể giúp bạn có thông điệp riêng cho từng form, và fallback về mã chung khi không có.

Tên `signupForm` là tên model attribute trong controller. Nếu đổi tên nó, key cụ thể có thể đổi; kiểm tra `FieldError.getCodes()` trong test thay vì chỉ phỏng đoán.

### 7.2. Jakarta Validation có tệp riêng

Một constraint có message template:

~~~java
@NotBlank(message = "{customer.name.required}")
private String name;
~~~

Khi dùng `jakarta.validation.Validator` với MessageInterpolator mặc định, key `customer.name.required` thông thường được tìm trong:

~~~text
src/main/resources/ValidationMessages.properties
src/main/resources/ValidationMessages_vi.properties
src/main/resources/ValidationMessages_en.properties
~~~

Ví dụ:

~~~properties
# ValidationMessages.properties
customer.name.required=Customer name is required
~~~

~~~properties
# ValidationMessages_vi.properties
customer.name.required=Cần nhập tên khách hàng
~~~

**`messages*.properties` của Spring và `ValidationMessages*.properties` của Jakarta không mặc định là cùng một nguồn.** Chỉ vì có key trong `messages_vi.properties` không có nghĩa một lời gọi Jakarta Validator thuần sẽ đọc được nó.

### 7.3. Dùng chung thông điệp khi có chủ đích

Spring `LocalValidatorFactoryBean` hỗ trợ cấu hình `setValidationMessageSource(...)`:

~~~java
@Configuration
class ValidationConfiguration {

    @Bean
    LocalValidatorFactoryBean validator(
            MessageSource messages) {

        LocalValidatorFactoryBean bean =
                new LocalValidatorFactoryBean();
        bean.setValidationMessageSource(messages);
        return bean;
    }
}
~~~

Đoạn này là **snippet cấu hình độc lập về ý tưởng**, không nằm trong demo chạy được. Khi áp dụng thật cần imports, kiểm tra Spring Boot auto-configuration, không tạo nhiều validators cạnh tranh. Tránh bật `useCodeAsDefaultMessage` tùy tiện trên MessageSource dùng cho Jakarta interpolation: nó có thể khiến fallback tới thông điệp built-in của provider không diễn ra đúng kỳ vọng.

Một dự án nên quyết định rõ nguồn nội dung: messages cho UI và Spring FieldError, ValidationMessages cho Jakarta constraint templates, hoặc cấu hình bridge có kiểm thử.

## 8. Locale trong Spring MVC: Accept-Language

Spring MVC dùng một `LocaleResolver` để lấy locale của request. Với cấu hình phổ biến, client chọn qua:

~~~http
GET /signup/welcome?name=Lan
Accept-Language: vi-VN,vi;q=0.9,en;q=0.8
~~~

Handler có thể nhận `Locale`:

~~~java
@GetMapping("/welcome")
@ResponseBody
String welcome(@RequestParam String name,
               Locale locale) {
    return messageSource.getMessage(
            "signup.welcome",
            new Object[] {name},
            locale);
}
~~~

Snippet trên giả định đã inject `messageSource`.

**Không được nhầm `Accept-Language` với `?lang=vi`.** Nếu dùng `AcceptHeaderLocaleResolver`, query parameter `lang` không tự đổi locale. Muốn đổi qua query/session, cần `LocaleChangeInterceptor` kết hợp `LocaleResolver` hỗ trợ đổi locale, ví dụ `SessionLocaleResolver`, hoặc một chiến lược locale riêng của ứng dụng. `AcceptHeaderLocaleResolver` không hỗ trợ setLocale theo cách đó.

Trong background jobs hoặc message consumers, không có HTTP request để suy ra locale: truyền Locale tường minh hoặc dùng chính sách mặc định của nghiệp vụ. Locale chỉ điều khiển cách hiển thị, không phải chứng cứ authentication/authorization.

## 9. Project Java 17+ / Spring Boot 3.5.7

Ứng dụng minh họa có form name/email/age và hai endpoint text để test thông điệp có tham số cùng fallback vùng. Dùng Spring MVC, Thymeleaf và Jakarta Validation. **Không cần viết một bean MessageSource mới** khi file gốc `messages.properties` đã hiện diện.

### 9.1. Cấu trúc

~~~text
localized-signup/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/i18n/
    │   │   ├── Application.java
    │   │   ├── SignupForm.java
    │   │   └── SignupController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── messages.properties
    │       ├── messages_en.properties
    │       ├── messages_vi.properties
    │       ├── messages_vi_VN.properties
    │       └── templates/signup.html
    └── test/
        └── java/com/example/i18n/
            └── SignupControllerTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>localized-signup</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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
~~~

Đây là ứng dụng Servlet/Spring MVC, không phải WebFlux. Spring Boot quản lý dependency versions; dùng JDK 17+. Dự án production nên chọn bản vá Boot phù hợp chính sách hỗ trợ/bảo mật thay vì máy móc giữ đúng version demo.

### 9.3. Application.java

~~~java
package com.example.i18n;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 9.4. SignupForm.java

~~~java
package com.example.i18n;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SignupForm {

    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
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
~~~

Các annotations dùng default Jakarta constraint messages. Spring MVC tạo FieldError codes như `NotBlank.signupForm.name`; trong template, MessageSource có thể ưu tiên những keys đã định nghĩa trong `messages_vi.properties`.

### 9.5. SignupController.java

~~~java
package com.example.i18n;

import jakarta.validation.Valid;
import org.springframework.context.MessageSource;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import java.util.Locale;

@Controller
@RequestMapping("/signup")
public class SignupController {

    private final MessageSource messages;

    public SignupController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping
    public String form(Model model) {
        model.addAttribute("signupForm", new SignupForm());
        return "signup";
    }

    @PostMapping
    public String submit(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "signup";
        }
        return "redirect:/signup/success";
    }

    @GetMapping(
            value = "/welcome",
            produces = "text/plain;charset=UTF-8")
    @ResponseBody
    public String welcome(
            @RequestParam(defaultValue = "Lan") String name,
            Locale locale) {

        return messages.getMessage(
                "signup.welcome",
                new Object[] {name},
                locale);
    }

    @GetMapping(
            value = "/region",
            produces = "text/plain;charset=UTF-8")
    @ResponseBody
    public String region(Locale locale) {
        return messages.getMessage(
                "signup.region", null, locale);
    }

    @GetMapping(
            value = "/success",
            produces = "text/plain;charset=UTF-8")
    @ResponseBody
    public String success(Locale locale) {
        return messages.getMessage(
                "signup.success", null, locale);
    }
}
~~~

`@Valid` và `BindingResult` phải đứng liền nhau để controller xử lý lỗi form. Khi lỗi, return cùng view `signup` để giữ lại input/FieldError; khi hợp lệ, redirect. `Locale locale` được Spring MVC lấy theo request. `produces` có charset rõ cho những endpoint trả tiếng Việt trực tiếp.

### 9.6. application.properties

~~~properties
server.port=8080
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
spring.thymeleaf.cache=false
~~~

Tắt Thymeleaf cache chỉ để tiện học và sửa template.

### 9.7. messages.properties

~~~properties
# src/main/resources/messages.properties
signup.title=Sign up
signup.name=Full name
signup.email=Email
signup.age=Age
signup.submit=Submit
signup.success=Accepted
signup.welcome=Hello {0}!
signup.region=General message

NotBlank.signupForm.name=Name is required
NotBlank.signupForm.email=Email is required
Email.signupForm.email=Email is not valid
NotNull.signupForm.age=Age is required
Min.signupForm.age=Age must be at least 18
typeMismatch.signupForm.age=Age must be an integer
~~~

File gốc cung cấp bản dịch mặc định; các mã `NotBlank.signupForm.name` là Spring field-error codes, không phải tên file `ValidationMessages`.

### 9.8. messages_en.properties

~~~properties
# src/main/resources/messages_en.properties
signup.welcome=Hello {0}!
signup.region=English message
~~~

Hai key này override tệp gốc cho tiếng Anh. `signup.title` không có trong file en nên fallback thành `Sign up` từ `messages.properties`. File vùng/ngôn ngữ không nhất thiết sao chép hết keys nếu policy cho phép fallback.

### 9.9. messages_vi.properties

~~~properties
# src/main/resources/messages_vi.properties
signup.title=Đăng ký
signup.name=Họ và tên
signup.email=Email
signup.age=Tuổi
signup.submit=Gửi
signup.success=Đã tiếp nhận
signup.welcome=Chào {0}!
signup.region=Thông điệp chung cho tiếng Việt

NotBlank.signupForm.name=Tên không được để trống
NotBlank.signupForm.email=Cần nhập Email
Email.signupForm.email=Email không hợp lệ
NotNull.signupForm.age=Cần nhập tuổi
Min.signupForm.age=Tuổi phải từ 18
typeMismatch.signupForm.age=Tuổi phải là số nguyên
~~~

File tiếng Việt dùng UTF-8. Các keys chuyên biệt cho `signupForm` được Thymeleaf `th:errors` chọn thông qua Spring MessageSource; không phải tất cả validation exceptions ngoài MVC đều tự đọc file này.

### 9.10. messages_vi_VN.properties

~~~properties
# src/main/resources/messages_vi_VN.properties
signup.region=Thông điệp riêng cho Việt Nam
~~~

Locale `vi-VN` chọn key vùng cho `signup.region`, nhưng lấy `signup.title` từ file `messages_vi.properties` vì file vùng không định nghĩa key đó.

### 9.11. templates/signup.html

~~~html
<!DOCTYPE html>
<html lang="en"
      th:lang="${#locale.language}"
      xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="#{signup.title}">Sign up</title>
    <style>
        .error { color: #b00020; }
        .invalid { border: 1px solid #b00020; }
    </style>
</head>
<body>
<h1 th:text="#{signup.title}">Sign up</h1>

<form th:action="@{/signup}"
      th:object="${signupForm}"
      method="post">

    <div>
        <label for="name"
               th:text="#{signup.name}">Full name</label>
        <input type="text"
               th:field="*{name}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('name')}"
           th:errors="*{name}"></p>
    </div>

    <div>
        <label for="email"
               th:text="#{signup.email}">Email</label>
        <input type="text"
               th:field="*{email}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('email')}"
           th:errors="*{email}"></p>
    </div>

    <div>
        <label for="age"
               th:text="#{signup.age}">Age</label>
        <input type="text"
               inputmode="numeric"
               th:field="*{age}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('age')}"
           th:errors="*{age}"></p>
    </div>

    <button type="submit"
            th:text="#{signup.submit}">Submit</button>
</form>
</body>
</html>
~~~

- `#{signup.title}` tra thông điệp theo locale.
- `${signupForm}` là biến model của form.
- `*{name}` là property của object đang chọn.
- `th:errors` render những FieldError đã được resolve qua MessageSource.
- `th:field` dùng Spring binding status để hiện lại input, kể cả rejected value khi `age=abc` không thể chuyển thành Integer.
- `${#locale.language}` giúp attribute lang trong HTML khớp với ngôn ngữ.

Đừng thay `th:field` bằng việc chỉ đọc Java getter nếu cần giữ giá trị không hợp lệ. View dùng escaping phù hợp; tránh `th:utext` với dữ liệu chưa tin cậy để phòng XSS.

## 10. Chạy thử HTTP

Từ thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Gửi:

~~~bash
curl -s -H "Accept-Language: vi" \
  "http://localhost:8080/signup/welcome?name=Lan"

curl -s -H "Accept-Language: en" \
  "http://localhost:8080/signup/welcome?name=Lan"

curl -s -H "Accept-Language: vi-VN" \
  "http://localhost:8080/signup/region"

curl -s -H "Accept-Language: vi" \
  "http://localhost:8080/signup/region"

curl -s -H "Accept-Language: fr-FR" \
  "http://localhost:8080/signup/region"
~~~

Năm **response bodies** riêng biệt:

~~~text
Chào Lan!
Hello Lan!
Thông điệp riêng cho Việt Nam
Thông điệp chung cho tiếng Việt
General message
~~~

Lệnh `curl -s` không nhất thiết thêm newline; đây là năm chuỗi được liệt kê để dễ so sánh, không phải log output của Spring Boot.

### Lỗi form được dịch

~~~bash
curl -i -X POST "http://localhost:8080/signup" \
  -H "Accept-Language: vi" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=" \
  --data-urlencode "email=sai-email" \
  --data-urlencode "age=16"
~~~

HTML form sẽ có những câu lỗi:

~~~text
Tên không được để trống
Email không hợp lệ
Tuổi phải từ 18
~~~

Trong demo, controller chủ động trả lại view với HTTP 200 khi form sai. Đây là chính sách của handler, không có nghĩa mọi lỗi `@Valid` đều phải trả 200. Với `age=abc`, `BindingResult` có lỗi `typeMismatch` và có thể giữ rejected input `abc` cho `th:field`; thông báo hiển thị là `Tuổi phải là số nguyên`.

## 11. MockMvc kiểm thử locale và fallback

File `src/test/java/com/example/i18n/SignupControllerTest.java`:

~~~java
package com.example.i18n;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.MessageSource;
import org.springframework.context.NoSuchMessageException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.servlet.ModelAndView;

import java.util.Locale;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    MessageSource messages;

    @Test
    void vietnameseTitle() {
        assertEquals("Đăng ký", messages.getMessage(
                "signup.title", null,
                Locale.forLanguageTag("vi")));
    }

    @Test
    void englishTitleFallsBackToBase() {
        assertEquals("Sign up", messages.getMessage(
                "signup.title", null, Locale.ENGLISH));
    }

    @Test
    void regionOverrideWins() {
        assertEquals("Thông điệp riêng cho Việt Nam",
                messages.getMessage(
                    "signup.region", null,
                    Locale.forLanguageTag("vi-VN")));
    }

    @Test
    void unknownLocaleFallsBackToBase() {
        assertEquals("General message",
                messages.getMessage(
                    "signup.region", null,
                    Locale.forLanguageTag("fr-FR")));
    }

    @Test
    void welcomeUsesAcceptLanguage() throws Exception {
        mvc.perform(get("/signup/welcome")
                        .param("name", "Lan")
                        .header("Accept-Language", "vi"))
                .andExpect(status().isOk())
                .andExpect(content().string("Chào Lan!"));

        mvc.perform(get("/signup/welcome")
                        .param("name", "Lan")
                        .header("Accept-Language", "en"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello Lan!"));
    }

    @Test
    void formLabelsAreLocalized() throws Exception {
        mvc.perform(get("/signup")
                        .header("Accept-Language", "vi"))
                .andExpect(status().isOk())
                .andExpect(view().name("signup"))
                .andExpect(content().string(
                        containsString("Đăng ký")));
    }

    @Test
    void validationErrorsUseMessageCodes()
            throws Exception {

        mvc.perform(post("/signup")
                        .header("Accept-Language", "vi")
                        .param("name", "")
                        .param("email", "sai-email")
                        .param("age", "16"))
                .andExpect(status().isOk())
                .andExpect(view().name("signup"))
                .andExpect(model().attributeHasFieldErrors(
                        "signupForm", "name", "email", "age"))
                .andExpect(content().string(
                        containsString("Tên không được để trống")))
                .andExpect(content().string(
                        containsString("Email không hợp lệ")))
                .andExpect(content().string(
                        containsString("Tuổi phải từ 18")));
    }

    @Test
    void conversionErrorKeepsRawInput()
            throws Exception {

        var response = mvc.perform(post("/signup")
                        .header("Accept-Language", "vi")
                        .param("name", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "abc"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "signupForm", "age"))
                .andExpect(content().string(
                        containsString("Tuổi phải là số nguyên")))
                .andReturn();

        ModelAndView mav = response.getModelAndView();
        assertNotNull(mav);

        BindingResult errors = (BindingResult)
                mav.getModel().get(
                        BindingResult.MODEL_KEY_PREFIX
                        + "signupForm");
        assertNotNull(errors);

        FieldError conversion = errors.getFieldErrors("age")
                .stream()
                .filter(FieldError::isBindingFailure)
                .findFirst()
                .orElseThrow();

        assertEquals("abc", conversion.getRejectedValue());
        assertEquals("abc", errors.getFieldValue("age"));
    }

    @Test
    void validFormRedirects() throws Exception {
        mvc.perform(post("/signup")
                        .param("name", "Lan")
                        .param("email", "lan@example.com")
                        .param("age", "22"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/signup/success"));
    }

    @Test
    void missingCodeUsesExplicitFallback() {
        assertEquals("Fallback",
                messages.getMessage(
                        "missing.code", null, "Fallback",
                        Locale.ENGLISH));
    }

    @Test
    void missingCodeWithoutFallbackThrows() {
        assertThrows(NoSuchMessageException.class,
                () -> messages.getMessage(
                        "missing.code", null,
                        Locale.ENGLISH));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Bộ **11 tests** minh họa việc tìm file gốc, fallback en, override vi-VN, locale chưa hỗ trợ, MessageFormat `{0}`, nhãn HTML, lỗi Bean Validation/BindingResult tiếng Việt, typeMismatch, redirect và missing keys. Không phụ thuộc thứ tự violations. Nếu thêm Spring Security sau này, các POST tests có thể cần CSRF token; lỗi HTTP 403 do CSRF xảy ra trước khi controller validation chạy.

## 12. Nhiều nhóm thông điệp, caching và vận hành

Dự án lớn có thể chia tệp theo module:

~~~text
src/main/resources/
├── messages.properties
├── messages_vi.properties
└── i18n/
    ├── checkout.properties
    ├── checkout_vi.properties
    ├── validation.properties
    └── validation_vi.properties
~~~

~~~properties
spring.messages.basename=messages,i18n/checkout,i18n/validation
~~~

Các key như `checkout.payment.failed` và `signup.validation.age` tránh xung đột. Spring Boot 3.5 có tùy chọn `spring.messages.common-messages` cho những tài nguyên message không phụ thuộc locale; chỉ dùng khi thực sự có nhóm nội dung chung.

Spring Framework có `ResourceBundleMessageSource` dựa trên Java ResourceBundle và `ReloadableResourceBundleMessageSource` cho các use case muốn reload linh hoạt hơn. Với ứng dụng thông thường, không cần tự tạo bean chỉ để dùng `messages_vi.properties`. Thuộc tính:

~~~properties
spring.messages.cache-duration=10s
~~~

điều chỉnh caching, nhưng **không có nghĩa file bên trong JAR sẽ tự hot reload** khi sửa trên filesystem. Cần cơ chế resource ngoài JAR hoặc redeploy nếu muốn cập nhật bản dịch trong production.

`spring.messages.use-code-as-default-message=true` có ích để debug key còn thiếu, nhưng không nên làm cách che lỗi bản dịch trong production. Khi cùng MessageSource được dùng cho Jakarta validation interpolation, trả code thô còn có thể ảnh hưởng fallback mặc định của provider.

## 13. Checklist và lỗi phổ biến

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Template hiện `??signup.title??` | Key hoặc bundle không resolve | Kiểm tra basename, classpath, messages.properties |
| Chỉ có `messages_vi.properties` | Thiếu file gốc cho auto-configuration | Tạo messages.properties |
| `messages_vi-VN.properties` không được chọn | Sai convention tên file | Dùng messages_vi_VN.properties |
| `fr-FR` trả khác nhau giữa các máy | JVM locale fallback | Tắt fallback-to-system-locale |
| Tiếng Việt lỗi dấu | Encoding không đồng nhất | UTF-8 và test sau build |
| `{0}` không đổi thành tên | Không truyền args/escape sai | Dùng Object[] và MessageFormat |
| Dấu nháy đơn bị nuốt | MessageFormat quoting | Kiểm tra dấu `''` |
| `?lang=vi` không đổi locale | Chưa cấu hình strategy theo query | Accept-Language hoặc LocaleChangeInterceptor phù hợp |
| Constraint message vẫn tiếng Anh | Thiếu Spring field error key hoặc đang dùng Jakarta ValidationMessages | Kiểm tra getCodes() và hai họ bundles |
| Đổi model object name rồi message mất | Key chuyên biệt phụ thuộc objectName | Cập nhật keys hoặc fallback codes |
| Không thấy thay đổi sau khi sửa bundle | Cache/JAR | Kiểm tra reload strategy/redeploy |
| Duplicate keys giữa nhiều basenames | Key collision | Namespace và test precedence |
| Không có validation errors | Thiếu starter/constraint/@Valid | Kiểm tra Bean Validation provider và BindingResult |
| Bản dịch được xuất như HTML | Dùng unescaped output | Ưu tiên th:text và escape output chống XSS |
| Lộ email/token trong error | Echo nguyên invalid value | Chỉ phản hồi field/code/message đã được duyệt |

Checklist QA nên có file gốc, locale vi/en/vi-VN/fr, UTF-8, placeholder indexes, MessageFormat apostrophe, `FieldError.getCodes()` và response HTML thực tế. File vùng chỉ override những keys thật sự cần khác biệt; không cần sao chép mọi key nếu policy cho phép fallback.

## 14. Câu hỏi tự kiểm tra

**1.** Tại sao `messages.properties` cần tồn tại dù ứng dụng chủ yếu dùng tiếng Việt?  
Vì nó là fallback và giúp Spring Boot nhận diện basename khi auto-configure MessageSource.

**2.** `vi-VN` tìm message ở đâu?  
Theo thứ tự thông thường: `messages_vi_VN.properties` → `messages_vi.properties` → `messages.properties`.

**3.** `spring.messages.basename=i18n/ui` tương ứng file nào?  
`src/main/resources/i18n/ui.properties` và các biến thể như `ui_vi.properties` trên classpath.

**4.** `application.properties` có thay `messages.properties` không?  
Không. Một file chứa cấu hình, file còn lại chứa message keys và translations.

**5.** Hai overload `MessageSource.getMessage` có và không có default khác nhau thế nào?  
Có default cho fallback do caller chọn; không có default có thể ném `NoSuchMessageException`.

**6.** Vì sao `#{signup.title}` khác `${signupForm.name}`?  
`#{...}` tra message; `${...}` lấy model variable.

**7.** `ValidationMessages_vi.properties` dùng cho ai?  
Cho Jakarta Bean Validation MessageInterpolator theo convention, khác Spring message bundle thông thường.

**8.** Vì sao phải kiểm tra `FieldError.getCodes()`?  
Vì Spring có nhiều mã lỗi với độ cụ thể khác nhau và có thể thay đổi sau khi đổi object/field name.

**9.** Có thể chỉ dùng query `?lang=vi` để đổi locale theo cấu hình Accept-Language mặc định không?  
Không; cần locale resolution strategy hỗ trợ query.

**10.** Muốn response fallback giống nhau trên các máy chủ nên làm gì?  
Có file gốc, tắt system-locale fallback, test với locale chưa có translation.

## Kết luận

~~~text
message code signup.title
      |
      v
MessageSource + Locale
      |
      +-- messages_vi_VN.properties
      +-- messages_vi.properties
      +-- messages.properties
      |
      v
Đăng ký / Sign up / fallback

Spring MVC @Valid → BindingResult → FieldError codes
      |
      v
MessageSource → th:errors theo request locale
~~~

Giữ **basename ổn định**, file gốc, hậu tố đúng, UTF-8, fallback rõ ràng và các mã có namespace. Việc **dịch thông báo** và **kiểm tra điều kiện dữ liệu** là hai trách nhiệm độc lập: Spring MessageSource có thể dịch lỗi trong view, còn Jakarta Validation có bundle `ValidationMessages` theo convention riêng. Hãy kiểm chứng cả Java API và HTTP/HTML để chắc chắn người dùng thật sự thấy đúng ngôn ngữ.

## Tài liệu tham khảo

- [Spring Boot 3.5 — Internationalization](https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html)
- [Spring Framework — MessageSource API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/context/MessageSource.html)
- [Spring Framework — Error Code Resolution](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [Spring Framework — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Hibernate Validator 8 — Message interpolation](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-message-interpolation)
- [Java 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [Java 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html)

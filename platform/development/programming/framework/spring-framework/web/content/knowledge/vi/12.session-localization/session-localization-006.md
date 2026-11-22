# MessageSource, thông báo validation và bản địa hóa giao diện trong Spring MVC

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Spring MVC có form HTML, một màn hình có thể cần hiển thị cùng nội dung bằng tiếng Việt và tiếng Anh. Nhãn trường nhập, nút bấm, thông báo lỗi khi gửi form và thông báo lưu thành công đều cần bản dịch. Nếu viết cứng tất cả chuỗi trong controller hoặc view, mỗi lần hỗ trợ ngôn ngữ mới phải sửa logic ở nhiều nơi.

Spring cung cấp ba lớp trách nhiệm:

1. **Locale** mô tả ngôn ngữ/địa phương đang được sử dụng (ví dụ `vi`, `vi-VN`, `en`).
2. **LocaleResolver** xác định Locale của mỗi HTTP request; `LocaleChangeInterceptor` có thể hỗ trợ người dùng chọn ngôn ngữ qua query parameter khi resolver cho phép.
3. **MessageSource** tìm câu chữ từ các resource bundles theo message key và Locale; Spring MVC/Thymeleaf còn có cơ chế dùng MessageSource để hiện lỗi trong `BindingResult`.

Bài học tập trung vào **Spring Web MVC (Servlet stack)**, `MessageSource`, lỗi validation của form và i18n giao diện server-rendered bằng Thymeleaf. Ví dụ thực thi dùng Java 17, Spring Boot 3.3.5 và Spring Framework 6.1.x.

Một trải nghiệm mong muốn:

```text
GET /contacts/new?lang=vi
→ Tạo liên hệ / Họ và tên / Lưu liên hệ

GET /contacts/new?lang=en
→ Create contact / Name / Save contact

POST /contacts với name quá ngắn
→ vẫn hiển thị form, nhưng validation error được dịch
```

**i18n** là thiết kế ứng dụng có thể phục vụ nhiều ngôn ngữ; **l10n** là bản địa hóa nội dung/định dạng cho từng Locale. `MessageSource` không phải công cụ tự động dịch văn bản: người phát triển phải cung cấp các bản dịch và quy tắc fallback.

## 2. MessageSource và resource bundles

Interface `org.springframework.context.MessageSource` định nghĩa tra cứu message theo code, tham số và Locale:

```java
String getMessage(
        String code, Object[] args,
        String defaultMessage, Locale locale);

String getMessage(
        String code, Object[] args, Locale locale)
        throws NoSuchMessageException;

String getMessage(
        MessageSourceResolvable resolvable, Locale locale)
        throws NoSuchMessageException;
```

Đây là **trích chữ ký API**, chưa phải class Java độc lập có đủ imports. Giả sử tệp tiếng Việt có:

```properties
contact.heading=Tạo liên hệ
contact.saved=Đã lưu liên hệ {0}.
```

Tệp tiếng Anh:

```properties
contact.heading=Create contact
contact.saved=Saved contact for {0}.
```

Gọi:

```java
String vi = messageSource.getMessage(
    "contact.saved", new Object[]{"Lan"}, Locale.forLanguageTag("vi"));
String en = messageSource.getMessage(
    "contact.saved", new Object[]{"Lan"}, Locale.ENGLISH);
```

Kết quả:

```text
Đã lưu liên hệ Lan.
Saved contact for Lan.
```

`{0}` là tham số theo quy tắc `java.text.MessageFormat`. Lưu ý quy tắc escape dấu nháy đơn: trong pattern MessageFormat, hai dấu `''` có thể biểu thị một dấu nháy đơn; phải kiểm thử các bản dịch có apostrophe hoặc dấu ngoặc phức tạp.

Nếu không tìm được key:

- Overload có `defaultMessage` trả fallback được truyền vào.
- Overload không có default có thể ném `NoSuchMessageException`.
- Cấu hình `useCodeAsDefaultMessage` có thể hiện chính code, nhưng dùng nó bừa bãi sẽ che lỗi thiếu bản dịch.

Đừng dùng nội dung câu dịch làm identifier, ví dụ không đặt key là `Tạo liên hệ`. Nên đặt mã ổn định, mang ngữ nghĩa như `contact.heading`, `contact.submit`, `contact.error.email`.

### Spring Boot cấu hình MessageSource

Spring Boot tự cấu hình MessageSource nếu tìm thấy bundle cơ sở theo basename phù hợp, mặc định là `messages`. Có thể tạo:

```text
src/main/resources/
├── application.properties
├── messages.properties
├── messages_en.properties
└── messages_vi.properties
```

**Cần có `messages.properties`**, ngay cả khi phần lớn bản dịch nằm ở `messages_en.properties` và `messages_vi.properties`. Nếu chỉ cung cấp các file có hậu tố locale, auto-configuration của Boot có thể không được kích hoạt.

`application.properties`:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

- Basename có thể trỏ tới nhiều bundles, ví dụ `messages,validation`.
- UTF-8 giữ dấu tiếng Việt.
- `fallback-to-system-locale=false` giảm phụ thuộc vào locale của hệ điều hành chạy server; vẫn có thể rơi về bundle cơ sở.
- Resource bundle khác với cơ chế translate online: tải một tệp messages không khiến tất cả chuỗi trong database/UI tự động được dịch.

## 3. LocaleResolver và cách chọn ngôn ngữ cho request

Spring MVC giải quyết locale thông qua `LocaleResolver`:

| Resolver | Nguồn xác định locale | Dùng `?lang=vi` để thay đổi được không? |
| --- | --- | --- |
| `AcceptHeaderLocaleResolver` | HTTP `Accept-Language` của client | **Không** hỗ trợ `setLocale` qua interceptor |
| `SessionLocaleResolver` | Session attribute, sau đó fallback | **Có** |
| `CookieLocaleResolver` | Cookie client, sau đó fallback | **Có**, theo cookie policy |

Với ứng dụng chỉ đọc ngôn ngữ do browser gửi, `AcceptHeaderLocaleResolver` thường đủ; không cần tạo session chỉ để đọc header. Khi muốn có nút “Tiếng Việt / English” trên website truyền thống, `SessionLocaleResolver` đi với `LocaleChangeInterceptor` là cách dễ hiểu.

Cảnh báo: nếu chỉ thêm `LocaleChangeInterceptor` nhưng dùng `AcceptHeaderLocaleResolver`, việc đổi `?lang=vi` có thể gây `UnsupportedOperationException` vì server không thể thay HTTP `Accept-Language` trong request của trình duyệt.

Locale không phải timezone hay quốc tịch. Hai người dùng cùng `vi-VN` có thể ở múi giờ khác nhau. `Accept-Language` cũng không chứng minh danh tính người dùng; nó chỉ là preference của client.

## 4. BindingResult và việc bản địa hóa thông báo validation

Một form controller có thể có chữ ký:

```java
@PostMapping("/contacts")
public String submit(
        @Valid @ModelAttribute("contactForm") ContactForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "contacts/new";
    }
    return "redirect:/contacts/done";
}
```

Đây là **snippet**; controller đầy đủ ở phần 6. Thứ tự diễn ra:

```text
HTTP POST form fields
   |
   v
@ModelAttribute: binding chuỗi từ request vào ContactForm
   |
   v
@Valid: Jakarta Bean Validation kiểm tra constraints
   |
   v
BindingResult chứa FieldError hoặc ObjectError
   |
   v
Controller trả form view khi có lỗi
   |
   v
Thymeleaf th:errors và Spring MessageSource
   |
   v
Thông báo theo Locale của request
```

Điểm dễ nhầm là có **hai con đường tra message**:

1. **Bean Validation message interpolation** do provider (như Hibernate Validator) thực hiện khi xử lý annotation `@NotBlank(message = "...")`. Nguồn bundle chuẩn của Jakarta Validation thường là `ValidationMessages.properties`, hoặc có thể được nối với Spring MessageSource qua `LocalValidatorFactoryBean`.
2. **Spring MessageSource resolution trên `BindingResult`**: `FieldError` mang một danh sách **error codes** ưu tiên, và Thymeleaf `th:errors` có thể resolve các codes đó từ `messages*.properties` theo locale.

Ví dụ DTO có:

```java
@NotBlank
@Size(min = 2, max = 40)
private String name;
```

Lỗi `@NotBlank` cho `contactForm.name` thường có mã theo thứ tự ưu tiên như:

```text
NotBlank.contactForm.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
```

Khi `messages_vi.properties` chứa:

```properties
NotBlank.contactForm.name=Vui lòng nhập họ và tên.
Size.contactForm.name=Tên phải có từ 2 đến 40 ký tự.
```

thì Thymeleaf có thể hiển thị hai thông báo đó theo loại lỗi tương ứng. Không nhất thiết phải viết `message="Vui lòng nhập..."` trực tiếp trên Java DTO.

**Type conversion errors** cũng nằm trong BindingResult. Nếu form có `age` kiểu `int` mà người dùng nhập `xyz`, lỗi có thể mang code `typeMismatch.contactForm.age`; nó khác lỗi `@Min` hoặc `@NotNull`. Dịch lỗi validation cần hiểu mã nào thực sự được tạo ra.

`BindingResult` phải đứng **ngay sau** tham số `@Valid @ModelAttribute` liên quan nếu controller muốn nhận lỗi tại method. Nếu form sai và vẫn redirect, request mới sẽ không tự giữ BindingResult — cách đơn giản là render lại cùng view, giữ lỗi trong request hiện tại.

## 5. Phân biệt MessageSource arguments và validation placeholders

Thông điệp từ Spring MessageSource dùng `{0}`, `{1}`... theo MessageFormat:

```properties
contact.saved=Saved contact for {0}.
```

Bean Validation templates có thể dùng placeholders theo constraints, ví dụ `{min}`, `{max}`:

```java
@Size(min = 2, max = 40, message = "Length must be {min} to {max}")
private String name;
```

Nếu dùng Spring MessageSource để cấp messages cho Bean Validation, quá trình nội suy của provider và cách xử lý MessageFormat có thể tương tác. Đừng giả định việc đưa `{min}` vào bất kỳ file `messages.properties` nào cũng đồng nghĩa với `MessageSource.getMessage` tự biết giá trị `min`. Trong ví dụ runnable bên dưới, các lỗi hiển thị trên view dùng **Spring FieldError codes**, với thông báo tĩnh đầy đủ, để việc phân giải dễ đoán và kiểm chứng.

## 6. Ứng dụng chạy được: Java 17 + Spring MVC + Thymeleaf

Ứng dụng tạo liên hệ, cho phép đổi hai ngôn ngữ qua `?lang=vi`/`?lang=en`, dịch nhãn form và lỗi. Không dùng database; khi form hợp lệ, ứng dụng chỉ mô phỏng thao tác lưu rồi redirect.

### 6.1. Cấu trúc dự án

```text
mvc-i18n-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/i18n/
    │   │   ├── I18nApplication.java
    │   │   ├── LocaleConfig.java
    │   │   ├── ContactForm.java
    │   │   └── ContactController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── messages.properties
    │       ├── messages_en.properties
    │       ├── messages_vi.properties
    │       └── templates/contacts/
    │           ├── new.html
    │           └── done.html
    └── test/java/example/i18n/
        └── I18nWebTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>mvc-i18n-demo</artifactId>
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
```

**`src/main/java/example/i18n/I18nApplication.java`**

```java
package example.i18n;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class I18nApplication {
    public static void main(String[] args) {
        SpringApplication.run(I18nApplication.class, args);
    }
}
```

### 6.2. Cấu hình chọn ngôn ngữ qua session

**`src/main/java/example/i18n/LocaleConfig.java`**

```java
package example.i18n;

import java.util.Locale;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.i18n.LocaleChangeInterceptor;
import org.springframework.web.servlet.i18n.SessionLocaleResolver;

@Configuration
public class LocaleConfig implements WebMvcConfigurer {

    @Bean
    public LocaleResolver localeResolver() {
        SessionLocaleResolver resolver = new SessionLocaleResolver();
        resolver.setDefaultLocale(Locale.ENGLISH);
        return resolver;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        LocaleChangeInterceptor change = new LocaleChangeInterceptor();
        change.setParamName("lang");
        change.setHttpMethods("GET");
        registry.addInterceptor(change);
    }
}
```

Bean tên `localeResolver` cho phép MVC dùng `SessionLocaleResolver`. Khi người dùng truy cập `GET /contacts/new?lang=vi`, interceptor cập nhật locale của session. Mọi request sau cùng session (có cookie phù hợp) sẽ dùng locale đó. Default English cố định giúp ví dụ không phụ thuộc locale của máy chạy.

Nếu ứng dụng là REST stateless, việc đọc `Accept-Language` trực tiếp thường thích hợp hơn session. Nếu chỉ hỗ trợ `vi`/`en`, nên kiểm tra/giới hạn locale được phép từ input ở tầng thiết kế thật, thay vì cho mọi mã locale bất kỳ.

### 6.3. DTO và controller

**`src/main/java/example/i18n/ContactForm.java`**

```java
package example.i18n;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class ContactForm {
    @NotBlank
    @Size(min = 2, max = 40)
    private String name;

    @NotBlank
    @Email
    private String email;

    public ContactForm() {}

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

**`src/main/java/example/i18n/ContactController.java`**

```java
package example.i18n;

import java.util.Locale;
import java.util.Map;

import jakarta.validation.Valid;
import org.springframework.context.MessageSource;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/contacts")
public class ContactController {
    private final MessageSource messages;

    public ContactController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping("/new")
    public String newForm(Model model) {
        model.addAttribute("contactForm", new ContactForm());
        return "contacts/new";
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("contactForm") ContactForm form,
            BindingResult errors,
            RedirectAttributes redirectAttributes) {

        if (errors.hasErrors()) {
            return "contacts/new";
        }

        // Demo: không có repository, mô phỏng lưu thành công.
        redirectAttributes.addFlashAttribute(
                "savedName", form.getName().strip());
        return "redirect:/contacts/done";
    }

    @GetMapping("/done")
    public String done() {
        return "contacts/done";
    }

    @GetMapping("/label")
    @ResponseBody
    public Map<String, String> label(Locale locale) {
        String heading = messages.getMessage(
                "contact.heading", null, locale);
        return Map.of("heading", heading);
    }
}
```

Khi POST invalid, Spring giữ `ContactForm` và `BindingResult` trong model của request; controller render lại form. Khi hợp lệ, redirect tránh việc refresh gửi lại POST, còn flash `savedName` dành cho GET liền sau. Vì ứng dụng không lưu dữ liệu bền vững, endpoint done chỉ là ví dụ màn hình thông báo, không phải hệ thống tạo liên hệ thật.

Endpoint `GET /contacts/label` minh họa gọi `MessageSource` trực tiếp với `Locale` do MVC resolve. `@ResponseBody` là cần thiết vì class là `@Controller` và method này muốn trả JSON, không phải view.

### 6.4. Tất cả resource bundles

**`src/main/resources/application.properties`**

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

**`src/main/resources/messages.properties`** — fallback English:

```properties
contact.heading=Create contact
contact.name=Name
contact.email=Email
contact.submit=Save contact
contact.done=Completed
contact.saved=Saved contact for {0}.
NotBlank.contactForm.name=Name is required.
Size.contactForm.name=Name must have 2 to 40 characters.
NotBlank.contactForm.email=Email is required.
Email.contactForm.email=Enter a valid email address.
```

**`src/main/resources/messages_en.properties`**

```properties
contact.heading=Create contact
contact.name=Name
contact.email=Email
contact.submit=Save contact
contact.done=Completed
contact.saved=Saved contact for {0}.
NotBlank.contactForm.name=Name is required.
Size.contactForm.name=Name must have 2 to 40 characters.
NotBlank.contactForm.email=Email is required.
Email.contactForm.email=Enter a valid email address.
```

**`src/main/resources/messages_vi.properties`**

```properties
contact.heading=Tạo liên hệ
contact.name=Họ và tên
contact.email=Địa chỉ email
contact.submit=Lưu liên hệ
contact.done=Hoàn tất
contact.saved=Đã lưu liên hệ {0}.
NotBlank.contactForm.name=Vui lòng nhập họ và tên.
Size.contactForm.name=Tên phải có từ 2 đến 40 ký tự.
NotBlank.contactForm.email=Vui lòng nhập email.
Email.contactForm.email=Email không đúng định dạng.
```

Tên `contactForm` trong `NotBlank.contactForm.name` **phải trùng** tên model attribute truyền ở controller. Lỗi `@Size` cho name và `@Email` cho email sẽ có keys tương ứng. Một trường nhập sai có thể phát sinh nhiều errors; đừng mặc định lúc nào cũng chỉ có một `FieldError`.

### 6.5. Template Thymeleaf với messages và lỗi validation

**`src/main/resources/templates/contacts/new.html`**

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="#{contact.heading}">Create contact</title>
</head>
<body>
    <nav>
        <a th:href="@{/contacts/new(lang='vi')}">Tiếng Việt</a>
        <a th:href="@{/contacts/new(lang='en')}">English</a>
    </nav>
    <h1 th:text="#{contact.heading}">Create contact</h1>

    <form th:action="@{/contacts}"
          th:object="${contactForm}" method="post">
        <label for="name" th:text="#{contact.name}">Name</label>
        <input id="name" th:field="*{name}" type="text">
        <p th:if="${#fields.hasErrors('name')}"
           th:errors="*{name}">Name error</p>

        <label for="email" th:text="#{contact.email}">Email</label>
        <input id="email" th:field="*{email}" type="email">
        <p th:if="${#fields.hasErrors('email')}"
           th:errors="*{email}">Email error</p>

        <button type="submit" th:text="#{contact.submit}">
            Save contact
        </button>
    </form>
</body>
</html>
```

Ba kiểu biểu thức của Thymeleaf cần nhớ:

- `#{contact.heading}` tra message key trong bundles, dùng locale hiện tại.
- `${contactForm}` tham chiếu object trong Spring model.
- `*{name}` là một property của object do `th:object` chọn.

`th:field` giúp bind input, giữ giá trị khi form bị trả lại sau lỗi. `#fields.hasErrors('name')` và `th:errors="*{name}"` dựa trên Spring BindingResult, hiển thị thông báo sau khi resolve qua MessageSource.

Đây là trang demo có `html lang="en"` cố định; khi triển khai thực, cần gán lang phản ánh locale đang hiển thị, ví dụ expose `htmlLang` từ controller rồi dùng `th:lang="${htmlLang}"`. Điều này quan trọng với screen reader/accessibility, dù không ngăn message lookup hoạt động trong demo.

**`src/main/resources/templates/contacts/done.html`**

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="#{contact.done}">Completed</title>
</head>
<body>
    <h1 th:text="#{contact.done}">Completed</h1>
    <p th:if="${savedName}"
       th:text="#{contact.saved(${savedName})}">
       Saved contact
    </p>
    <a th:href="@{/contacts/new}"
       th:text="#{contact.heading}">Create contact</a>
</body>
</html>
```

`#{contact.saved(${savedName})}` đưa biến `savedName` vào placeholder `{0}` của message. Template dùng `th:text` để escape HTML; không dùng `th:utext` cho chuỗi do người dùng nhập. Flash attribute chỉ sống tạm sau redirect: khi refresh trang done, thông báo không bắt buộc xuất hiện lần nữa.

## 7. Chạy thử và đầu ra mong đợi

Ở thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Hai lệnh thực hiện **tuần tự**. Sau khi chạy, mở:

```text
http://localhost:8080/contacts/new?lang=vi
```

Các phần text chính:

```text
Tiếng Việt  English
Tạo liên hệ
Họ và tên
Địa chỉ email
Lưu liên hệ
```

Chọn liên kết English; cùng session, phần giao diện đổi thành:

```text
Tiếng Việt  English
Create contact
Name
Email
Save contact
```

Thử POST với `name=A` và `email=not-an-email`. `A` có một ký tự, vi phạm `@Size(min=2,max=40)`; `not-an-email` vi phạm `@Email`. Với locale tiếng Việt, các errors hiển thị theo bundle:

```text
Tên phải có từ 2 đến 40 ký tự.
Email không đúng định dạng.
```

Nếu form hợp lệ như `name=Lan`, `email=lan@example.com`, server trả redirect tới `/contacts/done`. Trên trang kết quả GET tiếp theo, thông báo dự kiến theo locale tiếng Việt là:

```text
Đã lưu liên hệ Lan.
```

Với locale English, kết quả tương ứng là:

```text
Saved contact for Lan.
```

Lưu ý browser phải giữ session cookie. Nếu đổi `?lang=vi` bằng trình duyệt A rồi dùng curl không có cookie của trình duyệt A, request curl có thể trở lại locale mặc định English.

### Gọi MessageSource trực tiếp qua API JSON minh họa

`GET /contacts/label` trả một JSON object:

```json
{"heading":"Tạo liên hệ"}
```

hoặc:

```json
{"heading":"Create contact"}
```

Tùy session Locale. Dùng curl với cookie jar trên Bash:

```bash
curl -s -c cookies.txt -b cookies.txt \
  'http://localhost:8080/contacts/new?lang=vi' > /dev/null

curl -s -b cookies.txt \
  'http://localhost:8080/contacts/label'
```

Response body thường là `{"heading":"Tạo liên hệ"}`. Trong PowerShell, cách gửi session cookies khác và `/dev/null` không phải đường null output chuẩn; có thể dùng `Invoke-WebRequest` với `-WebSession`.

## 8. MockMvc test: hai ngôn ngữ và validation

**`src/test/java/example/i18n/I18nWebTest.java`**

```java
package example.i18n;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.MessageSource;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class I18nWebTest {
    @Autowired MockMvc mvc;
    @Autowired MessageSource messages;

    @Test
    void messagesExistInEnglishAndVietnamese() {
        assertEquals("Create contact", messages.getMessage(
                "contact.heading", null, Locale.ENGLISH));
        assertEquals("Tạo liên hệ", messages.getMessage(
                "contact.heading", null, Locale.forLanguageTag("vi")));
    }

    @Test
    void vietnameseFormRendersTranslatedHeading() throws Exception {
        mvc.perform(get("/contacts/new").param("lang", "vi"))
           .andExpect(status().isOk())
           .andExpect(view().name("contacts/new"))
           .andExpect(content().string(containsString("Tạo liên hệ")));
    }

    @Test
    void englishFormRendersTranslatedHeading() throws Exception {
        mvc.perform(get("/contacts/new").param("lang", "en"))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("Create contact")));
    }

    @Test
    void invalidFormRendersVietnameseMessages() throws Exception {
        MockHttpSession session = (MockHttpSession) mvc
                .perform(get("/contacts/new").param("lang", "vi"))
                .andReturn().getRequest().getSession(false);

        mvc.perform(post("/contacts").session(session)
                        .param("name", "A")
                        .param("email", "not-an-email"))
           .andExpect(status().isOk())
           .andExpect(model().attributeHasFieldErrors(
                   "contactForm", "name", "email"))
           .andExpect(content().string(containsString(
                   "Tên phải có từ 2 đến 40 ký tự.")))
           .andExpect(content().string(containsString(
                   "Email không đúng định dạng.")));
    }

    @Test
    void validFormRedirects() throws Exception {
        mvc.perform(post("/contacts")
                        .param("name", "Lan")
                        .param("email", "lan@example.com"))
           .andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrl("/contacts/done"));
    }
}
```

Chạy `mvn test`. Class có **5 test methods**; nếu mọi test pass, Maven trả exit code `0`. Không dựa vào thứ tự chạy test, thông báo console hay thời gian. Test validation tạo một session qua GET `?lang=vi`, sau đó gửi POST **cùng session** để kiểm tra bản dịch thật ở view.

Trong dự án thực, nên bổ sung test từng message key được dịch đủ, missing-key fallback, locale không hỗ trợ, apostrophes, UI accessibility, việc đổi ngôn ngữ qua redirect, và các hình thức validation khác như `typeMismatch`.

## 9. Khi cần bản địa hóa thông báo ngay từ Bean Validation provider

Ở ví dụ form, lỗi hiển thị thông qua Spring `BindingResult` codes. Nếu bạn muốn lấy bản dịch **ngay tại `ConstraintViolation.getMessage()`** hoặc muốn annotation dùng custom template:

```java
@NotBlank(message = "{contact.name.required}")
private String name;
```

thì phải hiểu **Jakarta Bean Validation message interpolation** là cơ chế riêng. Theo thông lệ, provider đọc `ValidationMessages.properties` cùng các biến thể locale; Spring có thể kết nối `MessageSource` bằng `LocalValidatorFactoryBean.setValidationMessageSource(...)`.

Snippet cấu hình **tùy chọn**, dành cho dự án có nhu cầu này (không bắt buộc để chạy ví dụ phần 6):

```java
@Bean
public LocalValidatorFactoryBean applicationValidator(
        MessageSource messageSource) {
    LocalValidatorFactoryBean validator =
            new LocalValidatorFactoryBean();
    validator.setValidationMessageSource(messageSource);
    return validator;
}
```

Imports cần thiết:

```java
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
```

Khi dùng cấu hình tùy chọn này, bảo đảm MVC `@Valid` thật sự sử dụng validator đã được cấu hình (tùy ứng dụng có thể cần `WebMvcConfigurer.getValidator()`), không vô ý có nhiều validator beans cạnh tranh; phải chạy integration tests. Không cấu hình đồng thời `setValidationMessageSource` và `setMessageInterpolator` trên cùng factory khi hai lựa chọn không tương thích.

Thêm key vào các bundle:

```properties
contact.name.required=Please enter your name.
```

```properties
contact.name.required=Vui lòng nhập họ và tên.
```

Hai đoạn trên lần lượt thuộc `messages_en.properties` và `messages_vi.properties` khi áp dụng tùy chọn. Spring có thể dùng `LocaleContextHolder` của request cho message interpolation qua provider được tích hợp; nếu bạn dùng custom `ValidatorFactory` ở ngoài Spring hoặc xử lý async, locale phải được truyền/cấu hình đúng.

**Không nên suy luận** rằng mọi chuỗi của `FieldError.getDefaultMessage()` chắc chắn được locale hóa chỉ vì Thymeleaf hiển thị lỗi đúng. Với REST API, muốn một thông điệp cụ thể theo locale, có thể lấy `MessageSource.getMessage(error, locale)` (với `error` là `ObjectError` hoặc `FieldError` — tức `MessageSourceResolvable`), rồi trả một error DTO có `code` ổn định và `message` là bản dịch. Nếu kế thừa `ResponseEntityExceptionHandler`, hãy override handler thích hợp thay vì đăng ký `@ExceptionHandler` trùng với exception mà base class đã xử lý.

## 10. Formatting khác với translating

`MessageSource` phục vụ dịch **văn bản**. Khi hiển thị ngày, giờ, số hoặc tiền, dùng formatter/converter phù hợp. Ví dụ Java 17 hoàn chỉnh, chạy độc lập:

**`LocaleNumberDemo.java`**

```java
import java.text.NumberFormat;
import java.util.Locale;

public class LocaleNumberDemo {
    public static void main(String[] args) {
        double number = 1234.5;
        NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat germany = NumberFormat.getNumberInstance(Locale.GERMANY);
        us.setMinimumFractionDigits(2);
        germany.setMinimumFractionDigits(2);
        System.out.println(us.format(number));
        System.out.println(germany.format(number));
    }
}
```

Chạy:

```bash
javac LocaleNumberDemo.java
java LocaleNumberDemo
```

Kết quả điển hình trên JDK với CLDR locale data:

```text
1,234.50
1.234,50
```

Ví dụ dùng `double` chỉ để nhìn dấu số. Với tiền thật, nên dùng `BigDecimal` và quy tắc currency/rounding rõ ràng. Đừng đổi ý nghĩa `VND` thành `USD` chỉ bằng cách thay ký hiệu tiền.

Trong Spring MVC, `@DateTimeFormat`, `@NumberFormat`, `Formatter` và `ConversionService` hỗ trợ form binding/formatting; chúng giải quyết việc khác với tra message code.

## 11. Những giới hạn trong ứng dụng thực tế

### 11.1. Chọn ngôn ngữ không thay thế security

`lang` là dữ liệu request, có thể bị sửa tùy ý. Không coi locale là dấu hiệu quyền, quốc tịch hoặc phân vùng tenant. Nếu dùng session/cookie, cần hiểu CSRF, session lifetime, cache policy, và trạng thái người dùng. Nếu website cần ghi nhớ locale qua nhiều thiết bị, hãy cân nhắc preference trên tài khoản.

Với `spring-boot-starter-security` và session login, POST form có thể cần CSRF token; ví dụ không cài Spring Security nên không triển khai token. Đừng tắt CSRF ở ứng dụng thật chỉ để cho ví dụ POST chạy.

### 11.2. HTML escaping và accessibility

Thymeleaf `th:text` escape HTML đầu ra, giúp tránh nhiều lỗi XSS khi chèn dữ liệu người dùng vào câu dịch. Đừng dùng `th:utext` với nội dung chưa được sanitize. Cần thiết kế HTML `lang` theo locale thực, liên kết lỗi bằng `aria-describedby`/`aria-invalid` và kiểm tra với screen readers; một giao diện chỉ đổi text nhưng sai lang metadata vẫn là localization chưa hoàn chỉnh.

### 11.3. Caching và response representation

Nếu HTML/JSON phụ thuộc `Accept-Language`, CDN/reverse proxy có thể cần `Vary: Accept-Language` hoặc cache key theo locale; nếu locale trong session/cookie thì thường cần xử lý caching phù hợp dữ liệu cá nhân hóa. Không dùng một public cache key cho các response khác ngôn ngữ rồi để user A nhìn nội dung của user B.

### 11.4. Background jobs và thread context

`LocaleContextHolder` thường gắn locale vào thread request. Tác vụ gửi email chạy ở worker khác **không mặc nhiên nhận locale của request ban đầu**; cần truyền Locale của người nhận vào hàm xây nội dung. Đừng dùng locale mặc định của máy chủ để dịch email cho tất cả người dùng.

### 11.5. Pluralization và ngữ cảnh

`MessageFormat` hỗ trợ tham số nhưng không tự giải quyết mọi số nhiều, giống và ngữ pháp. Với ngôn ngữ phức tạp, cân nhắc ICU MessageFormat hoặc message variants phù hợp. Không ghép ngẫu nhiên từ đã dịch thành câu, vì thứ tự từ và văn phạm khác nhau giữa các ngôn ngữ.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| UI hiện `contact.heading` | Không có key hoặc resolver không tìm bundle | Kiểm tra basename, classpath, key, fallback |
| Chỉ có `messages_vi.properties`, không tự cấu hình MessageSource | Thiếu bundle mặc định `messages.properties` | Thêm base file và test bean |
| Tiếng Việt bị lỗi dấu | Sai encoding | Lưu UTF-8, đặt `spring.messages.encoding=UTF-8` |
| `?lang=vi` gây exception | Interceptor đổi locale trên `AcceptHeaderLocaleResolver` | Dùng `SessionLocaleResolver` hoặc resolver có setLocale |
| Form dùng locale khác validation message | Message source/validator locale khác, session không được gửi | Kiểm tra `BindingResult.codes`, locale resolver và cookie |
| `th:errors` hiện tiếng Anh dù label tiếng Việt | Thiếu key `Size.contactForm.name` hoặc tên model object sai | Kiểm tra `FieldError.getCodes()` và bundle |
| Không hiện lỗi sau submit | `BindingResult` sai vị trí hoặc controller redirect khi invalid | Đặt kế tiếp `@Valid`, render lại view |
| `@NotBlank(message="{key}")` hiện nguyên key | Jakarta validator không thấy bundle dùng cho interpolation | Dùng `ValidationMessages*.properties`/`LocalValidatorFactoryBean` |
| Error JSON không được dịch | Trả `getDefaultMessage()` trực tiếp | Dùng `MessageSource.getMessage(error, locale)` hoặc cấu hình validator |
| Chỉ đổi một page, page khác không đổi | Hardcode strings còn sót, cache hoặc session khác | Kiểm tra tất cả templates, bundles, HTTP headers |
| MessageFormat làm mất dấu apostrophe | Escape theo cú pháp single quote | Dùng `''` và viết tests |
| Flash message không còn sau refresh | Flash chỉ để chuyển dữ liệu ngắn hạn sang GET kế tiếp | Không dùng flash làm state bền vững |
| Trả nguyên `error.getRejectedValue()` trong lỗi | Echo dữ liệu nhạy cảm | Chỉ trả field/code/message an toàn, log tối thiểu |
| Định dạng số đúng nhưng đơn vị tiền sai | Locale bị dùng thay cho currency nghiệp vụ | Mang currency riêng và định dạng theo business context |

Cách debug có hệ thống:

1. In/kiểm tra Locale do `LocaleResolver` trả về.
2. Xác nhận đủ `messages.properties`, `messages_en.properties`, `messages_vi.properties` trên classpath.
3. Kiểm tra `spring.messages.basename` và encoding.
4. Unit-test `messageSource.getMessage("contact.heading", null, locale)`.
5. Đối với validation, inspect `BindingResult.getFieldError("name").getCodes()` và các key được tìm trong bundle.
6. Phân biệt `FieldError.getDefaultMessage()` và `MessageSource.getMessage(error, locale)`.
7. Render HTML và kiểm tra `th:errors` theo hai locale, không chỉ đọc JSON/Java object.
8. Giữ cùng session khi đổi ngôn ngữ qua `?lang=...`; test cả fallback locale.
9. Kiểm tra chỗ nào còn hardcode, bị cache, hoặc sử dụng locale từ background thread sai ngữ cảnh.
10. Khi có API công khai, định nghĩa error code ổn định; đừng bắt client parse nội dung đã dịch.

## 13. Checklist trước khi triển khai i18n

1. Các message keys được đặt theo domain/action, không phụ thuộc trực tiếp vào câu đã dịch.
2. Bundle cơ sở luôn có; bundles cho các ngôn ngữ được hỗ trợ tương đối đầy đủ.
3. Mọi file được lưu UTF-8; test dấu tiếng Việt/apostrophe.
4. Resolver được chọn đúng theo nhu cầu: browser header, session hoặc cookie.
5. Language switch không xung đột với `AcceptHeaderLocaleResolver`.
6. Validation tests assert đúng field code và message theo locale.
7. Logic POST hợp lệ dùng PRG khi phù hợp, form lỗi giữ `BindingResult`.
8. Error JSON tách machine-readable code khỏi localized text.
9. HTML `lang`, labels và errors hỗ trợ accessibility.
10. Ngày/tiền/đơn vị và timezone được định dạng theo quy tắc riêng.
11. Caching, CSRF, authentication và session được kiểm tra riêng.
12. Background jobs nhận Locale người dùng rõ ràng, không phụ thuộc default server thread.

## 14. Bài tập tự kiểm tra

1. `LocaleResolver` và `MessageSource` khác nhau ra sao?
2. Vì sao Spring Boot cần bundle mặc định `messages.properties`?
3. `#{contact.heading}` và `${contactForm}` khác gì nhau trong Thymeleaf?
4. Vì sao `NotBlank.contactForm.name` dùng cho `BindingResult` không hoàn toàn giống `@NotBlank(message="{contact.name.required}")`?
5. Vì sao `?lang=vi` có thể lỗi nếu dùng `AcceptHeaderLocaleResolver`?
6. Khi validation fail, làm sao giữ các lỗi trên trang HTML?
7. Vì sao nên test locale bằng cùng session nếu dùng `SessionLocaleResolver`?
8. `MessageSource.getMessage(error, locale)` hữu ích thế nào khi tạo JSON error response?
9. Vì sao Locale không tự quyết định timezone và đơn vị tiền?
10. Khi gửi email từ async job, bạn nên lấy Locale từ đâu?

**Gợi ý:** (1) Resolver chọn Locale, MessageSource trả văn bản. (2) Làm fallback và điều kiện auto-configuration. (3) Message key và model attribute. (4) Spring field error codes so với Jakarta Bean Validation interpolation. (5) Header không sửa được từ server. (6) Dùng `BindingResult` ngay sau `@Valid @ModelAttribute` rồi render cùng form. (7) Lựa chọn ngôn ngữ được lưu trong session. (8) Tra thông báo từ error codes theo locale, thay vì dùng defaultMessage tùy provider. (9) Cần giữ dữ liệu nghiệp vụ/currency/timezone riêng. (10) Lưu user preference hoặc truyền Locale tường minh cho worker.

## 15. Tài liệu chính thức

- [Spring Framework — MessageSource interface](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/MessageSource.html)
- [Spring Framework — MVC Locale Resolution](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html)
- [Spring Framework — Binding and Validation](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring Framework — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Framework — SessionLocaleResolver](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/i18n/SessionLocaleResolver.html)
- [Spring Framework — LocaleChangeInterceptor](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/i18n/LocaleChangeInterceptor.html)
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html)
- [Thymeleaf — Using Thymeleaf: Message Expressions](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html)
- [Jakarta Bean Validation 3.0](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)

**Tổng kết:** Spring MVC dùng `LocaleResolver` để xác định ngôn ngữ request, `MessageSource` để lấy văn bản theo code, và `BindingResult`/Thymeleaf để hiển thị lỗi form đã bản địa hóa. Cần hiểu sự khác nhau giữa việc resolve `FieldError` và nội suy message của Bean Validation provider; một ứng dụng đa ngôn ngữ hoàn chỉnh phải xử lý cả fallback, encoding, HTTP sessions, accessibility và test thật ở từng locale.

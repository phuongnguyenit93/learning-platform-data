# Thực hành trang biểu mẫu: View, bản địa hóa, session và redirect trong Spring MVC

## 1. Bài toán thực hành và kết quả cần đạt

Một trang biểu mẫu web truyền thống có nhiều trách nhiệm hơn việc nhận vài chuỗi rồi gọi service. Spring MVC phải hiển thị view HTML, bind các field từ form vào đối tượng Java, kiểm tra dữ liệu, giữ dữ liệu người dùng đang nhập, chọn ngôn ngữ giao diện, duy trì trạng thái qua nhiều request và điều hướng sau khi lưu thành công.

Trong bài này, ta xây dựng **trang đăng ký có chức năng lưu bản nháp**:

1. Người dùng mở `GET /form`, thấy trang Thymeleaf bằng tiếng Anh.
2. Chọn liên kết `?lang=vi`, nhãn và thông báo chuyển sang tiếng Việt và được nhớ trong HTTP session.
3. Nhập tên, email, ghi chú, chọn **Lưu bản nháp**; server giữ bản nháp trong session rồi redirect về `GET /form`.
4. Chọn **Gửi đăng ký**; nếu tên/email không hợp lệ, server render lại form cùng lỗi mà không redirect.
5. Nếu dữ liệu hợp lệ, server đánh dấu hoàn tất, xóa bản nháp thuộc controller khỏi session, đặt thông báo flash rồi redirect `GET /done`. Làm mới trang kết quả không tự gửi lại POST.

Bài minh họa **Spring MVC Servlet + Thymeleaf + Jakarta Bean Validation**, dùng Java 17 và Spring Boot 3.3.x (Spring Framework 6.1). Demo không ghi database: “hoàn tất” chỉ xác nhận luồng HTTP/view hoạt động. Ứng dụng production cần tầng service, transaction, bảo mật và idempotency riêng.

Mục tiêu kiến thức: hiểu `Model`, logical view name, `th:object`/`th:field`, `MessageSource` và locale, `@SessionAttributes`/`SessionStatus`, `RedirectAttributes.addFlashAttribute`, Post/Redirect/Get (PRG), cùng cách kiểm thử các giai đoạn của biểu mẫu bằng MockMvc.

## 2. Luồng request của một MVC form

~~~mermaid
flowchart TD
    A[GET /form] --> B[DispatcherServlet]
    B --> C[Controller trả logical view 'form']
    C --> D[Thymeleaf render HTML từ model + messages]
    D --> E[Trình duyệt hiển thị form]
    E --> F{POST /form với action}
    F -->|save| G[Bind draft và giữ trong session]
    G --> H[Flash saved=true]
    H --> I[302 Location: /form]
    I --> A
    F -->|finish| J[Bind + Jakarta Validation]
    J -->|Sai| K[BindingResult có field errors]
    K --> C
    J -->|Đúng| L[SessionStatus.setComplete]
    L --> M[Flash completedName]
    M --> N[302 Location: /done]
    N --> O[GET /done render view 'done']
~~~

Đây là luồng HTTP nhiều request. **View** do template engine render thành HTML; **model** chứa các dữ liệu template được phép truy cập. Khi controller trả `"form"`, Spring dùng view resolver tìm template (ví dụ `templates/form.html`). Khi trả `"redirect:/form"`, Spring phát HTTP redirect để browser **gửi request GET mới**; đây không phải hành vi render view `form` ngay trong POST.

| Controller trả về | Spring làm gì? | URL trên trình duyệt |
| --- | --- | --- |
| `"form"` | Render template `form.html` trong request hiện tại | Giữ URL request |
| `"done"` | Render template `done.html` | Giữ URL request |
| `"redirect:/form"` | Gửi redirect với Location `/form` | Browser đi sang URL `/form` |
| `"forward:/form"` | Chuyển request phía server cho handler khác | Browser thường không đổi URL |

Dùng redirect sau **POST thành công**, không redirect mù khi `BindingResult` có lỗi. Nếu redirect khi validation thất bại mà không chủ động giữ `BindingResult` và form values, các lỗi/giá trị nhập sẽ biến mất. Trả trực tiếp view `form` trên lỗi vừa đơn giản vừa giữ được kết quả bind của request.

## 3. View Thymeleaf, binding và kiểm tra dữ liệu

### 3.1. Model và template

Trong Spring Boot với starter Thymeleaf, file `src/main/resources/templates/form.html` là view HTML; controller trả logical view name `"form"`. Template nhận model attributes do controller cung cấp. Ví dụ một đoạn Thymeleaf:

~~~html
<form th:action="@{/form}" th:object="${draft}" method="post">
  <input type="text" th:field="*{name}">
  <span th:if="${#fields.hasErrors('name')}"
        th:errors="*{name}">Lỗi tên</span>
  <button name="action" value="finish" type="submit">Gửi</button>
</form>
~~~

Đây là fragment để hiểu cú pháp, không phải trang hoàn chỉnh. Dấu `th:object` trỏ đến **model attribute** `draft`. `th:field` sinh tên/id/giá trị tương ứng thuộc tính của object; nếu Spring bind lỗi, template hiển thị lại giá trị người dùng nhập và `BindingResult` phù hợp.

Cần phân biệt:
- HTML `name="action"` là một **tham số điều khiển nút submit** (`save` hoặc `finish`) do browser gửi.
- `name`, `email`, `note` là fields thuộc `draft`, được bind qua setter của JavaBean.
- `@Valid` kích hoạt Bean Validation trên object tại handler submit cuối; `BindingResult` phải nằm **ngay sau** argument được validate.
- `th:errors` lấy thông điệp lỗi từ Bean Validation/binding, còn `#{form.title}` đọc thông điệp UI từ message bundle.

### 3.2. Ranh giới client và server

Thuộc tính HTML như `required`, `maxlength` cải thiện UX nhưng có thể bị bỏ qua bởi cURL, bot hoặc client tự viết. Ràng buộc phải được kiểm lại ở server bằng `@NotBlank`, `@Email`, `@Size` và kiểm tra nghiệp vụ.

Các trường `id`, `role`, `price`, `owner` không nên xuất hiện trong một form object nhận tự do nếu client không được quyền sửa. Dùng DTO dành riêng cho input; tuyệt đối không bind trực tiếp toàn bộ entity có field nhạy cảm.

## 4. Bản địa hóa: MessageSource, LocaleResolver, interceptor

Spring MVC chọn `Locale` cho request rồi chuyển cho Spring message resolver và template engine. Ví dụ có `messages.properties` (tiếng Anh mặc định) và `messages_vi.properties` (tiếng Việt):

~~~properties
form.title=Registration form
form.name=Name
form.submit=Submit registration
~~~

~~~properties
form.title=Biểu mẫu đăng ký
form.name=Họ tên
form.submit=Gửi đăng ký
~~~

Trong view Thymeleaf, `<h1 th:text="#{form.title}">` sẽ hiện chuỗi theo locale hiện hành. **MessageSource** quản lý chuỗi giao diện; nó không tự dịch nội dung cơ sở dữ liệu hoặc tự chọn ngôn ngữ của lỗi nghiệp vụ chưa được thiết kế i18n.

Hai chiến lược phổ biến:
- `AcceptHeaderLocaleResolver`: suy ra locale từ header `Accept-Language`; phù hợp nếu muốn người dùng thay ngôn ngữ qua browser/header. Resolver này **không hỗ trợ thay locale bằng interceptor setLocale** theo cách thông thường.
- `SessionLocaleResolver`: đọc/ghi locale tùy chọn trong `HttpSession`; phù hợp ví dụ có session. `LocaleChangeInterceptor` nhìn `?lang=vi` hoặc `?lang=en` và gọi resolver thay đổi ngôn ngữ, duy trì cho các request sau thuộc cùng session.

Trong demo sử dụng `SessionLocaleResolver`. Khi session hết hạn hoặc browser mất cookie, ngôn ngữ trở về fallback (ở đây mặc định tiếng Anh). Cần cung cấp lựa chọn ngôn ngữ rõ ràng, giới hạn danh sách locale được hỗ trợ ở production và kiểm thử mọi message key cần thiết.

**Thông điệp validation** là resource bundle riêng trong ví dụ (`ValidationMessages.properties`, `ValidationMessages_vi.properties`) dùng các key trong annotation constraint. Nhờ đó test được cả nhãn UI lẫn thông báo ràng buộc theo ngôn ngữ thay vì hardcode tiếng Anh trong Java.

## 5. Session, flash attributes và chuyển hướng: ba vòng đời khác nhau

### 5.1. @SessionAttributes và SessionStatus

`@SessionAttributes("draft")` đặt trên **controller class** báo Spring lưu model attribute tên `draft` vào HTTP session giữa các request thuộc workflow đó. Khi `@ModelAttribute("draft")` xuất hiện lần đầu, object được tạo và lưu; các GET/POST tiếp theo lấy lại object từ session.

`SessionStatus.setComplete()` đánh dấu workflow đã hoàn thành để Spring **xóa model attributes do @SessionAttributes quản lý** sau handler. Nó **không gọi `HttpSession.invalidate()`**, vì làm vậy sẽ xóa cả đăng nhập, locale và trạng thái workflow khác của người dùng. Bản nháp là trạng thái tạm thời; ứng dụng vẫn phải xử lý khi session timeout hoặc dữ liệu từ tab khác cùng session ghi đè.

Đừng nhầm:
- `@SessionAttributes` (số nhiều, cấp class): chọn model attributes Spring tự quản lý cho workflow controller.
- `@SessionAttribute` (số ít, method parameter): đọc một session attribute đã tồn tại và thường do thành phần khác quản lý.
- `HttpSession`: API Servlet để đọc/ghi/xóa dữ liệu session thủ công, thích hợp khi sở hữu trạng thái rõ ràng.
- `SessionLocaleResolver`: cũng dùng HTTP session nhưng lưu **locale** riêng, không phải bản nháp `draft`.

Session thường được định danh qua cookie `JSESSIONID`, nhưng không có nghĩa dữ liệu session nhất thiết nằm trong cookie; với Servlet thông thường dữ liệu ở phía server. Khi chạy nhiều instance, cần chính sách session stickiness hoặc shared session storage (ví dụ Spring Session với Redis) và lưu ý serialization/TTL.

### 5.2. RedirectAttributes và flash

Sau khi lưu bản nháp, ta thêm `saved=true` qua `RedirectAttributes.addFlashAttribute`. Spring lưu flash attributes **tạm thời** cho request sau redirect (thường sử dụng session/FlashMap), chuyển chúng vào model của GET kế tiếp rồi loại bỏ. Đây là cơ chế truyền trạng thái UI ngắn hạn như “đã lưu”, không phải kho lưu trữ workflow lâu dài.

Trong demo, `completedName` chỉ hiện trên trang kết quả ngay sau POST hợp lệ. Nó **không nằm trong query string** vì được gửi dưới dạng flash. Nếu user truy cập trực tiếp `GET /done` mà không có flash, controller redirect về `/form`.

Phân biệt:
- `redirectAttributes.addAttribute("id", id)`: thích hợp cho tham số path/query (có thể lộ trong URL, bookmark, log).
- `redirectAttributes.addFlashAttribute("saved", true)`: dữ liệu tạm truyền qua một lần redirect, không đưa vào query.
- `@SessionAttributes("draft")`: giữ dữ liệu nhiều request cho tới khi gọi `setComplete()`.
- Model bình thường: mặc định chỉ tồn tại trong phạm vi một request để render view.

### 5.3. Post/Redirect/Get và giới hạn

Nếu POST trả HTML trực tiếp, người dùng F5 có thể bị browser hỏi gửi lại POST. Với **PRG**, POST thành công trả redirect, browser truy cập GET, nên F5 trên trang GET không tự gửi lại POST. Tuy nhiên PRG **không bảo đảm xử lý giao dịch exactly-once**: double-click hai POST, retry từ client hoặc request song song vẫn có thể tạo tác dụng phụ trùng. Khi thực sự ghi DB/thanh toán, cần transaction, unique key/idempotency, kiểm soát race và validation nghiệp vụ.

Đối với POST thất bại do validation, trả view trực tiếp để giữ `BindingResult`; nếu cần redirect cả lúc lỗi, phải có cơ chế lưu lỗi/giá trị riêng, nhưng thường phức tạp không cần thiết.

## 6. Dự án Java 17/Spring Boot 3.3 có thể chạy

Ta tạo một ứng dụng Servlet MVC nhỏ, một controller cho form session workflow và controller khác cho trang kết quả. Việc tách **DoneController** giúp `GET /done` không tự khởi tạo lại `draft` qua phương thức `@ModelAttribute` của FormController sau khi session workflow được xóa.

### 6.1. Cấu trúc thư mục

~~~text
mvc-form-i18n-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── FormDemoApplication.java
    │   │   ├── WebConfig.java
    │   │   ├── RegistrationDraft.java
    │   │   ├── FormController.java
    │   │   └── DoneController.java
    │   └── resources/
    │       ├── messages.properties
    │       ├── messages_vi.properties
    │       ├── ValidationMessages.properties
    │       ├── ValidationMessages_vi.properties
    │       └── templates/
    │           ├── form.html
    │           └── done.html
    └── test/java/demo/
        └── FormFlowTest.java
~~~

Tất cả classes cùng package `demo` nên Spring Boot component scan được controllers/configuration. Demo không cần repository hay database.

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-form-i18n-demo</artifactId>
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

Maven dependencies gồm MVC/Tomcat, Thymeleaf view resolver, Jakarta Bean Validation và JUnit/MockMvc. Version `3.3.13` được cố định để minh họa các API Spring 6.1; với dự án production hãy chọn nhánh còn được hỗ trợ theo chính sách cập nhật của tổ chức.

### 6.3. FormDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FormDemoApplication.class, args);
    }
}
~~~

Lớp này mở application context và embedded web server. Không cần `@EnableWebMvc` khi dùng cấu hình mặc định của Spring Boot: thêm annotation đó có thể vô tình làm mất một số MVC auto-configuration và view/converter mặc định.

### 6.4. WebConfig.java: chọn locale bằng session

~~~java
package demo;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.i18n.LocaleChangeInterceptor;
import org.springframework.web.servlet.i18n.SessionLocaleResolver;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Bean
    public LocaleResolver localeResolver() {
        SessionLocaleResolver resolver = new SessionLocaleResolver();
        resolver.setDefaultLocale(Locale.ENGLISH);
        return resolver;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        LocaleChangeInterceptor interceptor = new LocaleChangeInterceptor();
        interceptor.setParamName("lang");
        registry.addInterceptor(interceptor);
    }
}
~~~

Mặc định `lang=en`/không có lựa chọn riêng sẽ lấy English. Request `GET /form?lang=vi` khiến interceptor đổi locale đã lưu trong HTTP session. Các request cùng session sau đó không cần thêm tham số. Trong code này, chỉ các locale mà người dùng có bundle được thiết kế đầy đủ là `en` và `vi`; bản production nên giới hạn đúng danh sách lựa chọn, thay vì chấp nhận tùy ý một locale string.

### 6.5. RegistrationDraft.java: input DTO cho biểu mẫu

~~~java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RegistrationDraft {

    @NotBlank(message = "{form.name.required}")
    @Size(max = 80, message = "{form.name.length}")
    private String name = "";

    @NotBlank(message = "{form.email.required}")
    @Email(message = "{form.email.invalid}")
    private String email = "";

    @Size(max = 200, message = "{form.note.length}")
    private String note = "";

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

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
~~~

Các field được bind bởi Spring thông qua setters. `@NotBlank` từ chối null, chuỗi rỗng hoặc whitespace; `@Email` kiểm một số quy tắc định dạng email nhưng **không xác nhận mailbox tồn tại**. `@Size` giới hạn độ dài khi validate. Nút **Lưu bản nháp** bên dưới không chạy full validation, vì có thể lưu bản nháp đang thiếu dữ liệu; production cần giới hạn kích thước request ở tầng HTTP và kiểm soát dữ liệu session để tránh bị lạm dụng lưu payload quá lớn.

### 6.6. FormController.java: tạo, giữ và kết thúc draft

~~~java
package demo;

import jakarta.validation.Valid;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.SessionAttributes;
import org.springframework.web.bind.support.SessionStatus;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/form")
@SessionAttributes("draft")
public class FormController {

    @ModelAttribute("draft")
    public RegistrationDraft draft() {
        return new RegistrationDraft();
    }

    @GetMapping
    public String showForm() {
        return "form";
    }

    @PostMapping(params = "action=save")
    public String saveDraft(
            @ModelAttribute("draft") RegistrationDraft draft,
            RedirectAttributes redirect) {

        // @SessionAttributes tự giữ draft qua các request cùng session.
        // Không validate bắt buộc để cho phép lưu bản nháp chưa hoàn chỉnh.
        redirect.addFlashAttribute("saved", true);
        return "redirect:/form";
    }

    @PostMapping(params = "action=finish")
    public String finish(
            @Valid @ModelAttribute("draft") RegistrationDraft draft,
            BindingResult errors,
            RedirectAttributes redirect,
            SessionStatus sessionStatus) {

        if (errors.hasErrors()) {
            // Cùng request, giữ BindingResult và field values cho Thymeleaf.
            return "form";
        }

        // Demo chỉ xác nhận form, chưa lưu database.
        redirect.addFlashAttribute(
            "completedName", draft.getName().trim());
        sessionStatus.setComplete();
        return "redirect:/done";
    }
}
~~~

Không cần gọi `model.addAttribute("draft", ...)` trong GET vì phương thức `@ModelAttribute("draft")` tạo model object khi thiếu. Khi có `draft` trong session, Spring lấy lại object cũ. **Cùng một trình duyệt/cùng session dùng nhiều tab có thể chia sẻ draft**, nên một workflow production phức tạp có thể cần workflow ID riêng thay cho một tên session attribute cố định.

`BindingResult` đứng ngay sau `@Valid @ModelAttribute`; nếu đặt sai vị trí, Spring có thể không chuyển field errors vào argument như mong đợi. Còn `SessionStatus.setComplete()` chỉ được gọi sau khi form hợp lệ, tránh mất draft khi người dùng cần sửa lỗi.

### 6.7. DoneController.java: tránh kết quả rỗng khi vào thẳng URL

~~~java
package demo;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class DoneController {

    @GetMapping("/done")
    public String done(Model model) {
        if (!model.containsAttribute("completedName")) {
            return "redirect:/form";
        }
        return "done";
    }
}
~~~

Flash attribute `completedName` được chuyển sang model của GET ngay sau redirect. Nếu người dùng F5 khi flash đã hết, controller có thể chuyển về form vì không còn marker hoàn tất. Trong ứng dụng có database, nên dùng **ID của kết quả đã lưu và trang GET idempotent**, thay vì phụ thuộc hoàn toàn vào flash để xem lại dữ liệu sau vài phút.

### 6.8. Các resource bundles cho UI và validation

**src/main/resources/messages.properties**:

~~~properties
form.title=Registration form
form.language=Language
form.name=Full name
form.email=Email address
form.note=Notes
form.save=Save draft
form.finish=Submit registration
form.saved=Draft saved in this session.
form.done.title=Registration completed
form.done.message=Registration received for:
form.new=Start another registration
~~~

**src/main/resources/messages_vi.properties**:

~~~properties
form.title=Biểu mẫu đăng ký
form.language=Ngôn ngữ
form.name=Họ và tên
form.email=Địa chỉ email
form.note=Ghi chú
form.save=Lưu bản nháp
form.finish=Gửi đăng ký
form.saved=Đã lưu bản nháp trong phiên hiện tại.
form.done.title=Đăng ký hoàn tất
form.done.message=Đã nhận đăng ký của:
form.new=Tạo đăng ký khác
~~~

**src/main/resources/ValidationMessages.properties**:

~~~properties
form.name.required=Please enter your name.
form.name.length=Name must not exceed {max} characters.
form.email.required=Please enter your email.
form.email.invalid=Email format is invalid.
form.note.length=Notes must not exceed {max} characters.
~~~

**src/main/resources/ValidationMessages_vi.properties**:

~~~properties
form.name.required=Vui lòng nhập tên.
form.name.length=Tên không được vượt quá {max} ký tự.
form.email.required=Vui lòng nhập email.
form.email.invalid=Định dạng email không hợp lệ.
form.note.length=Ghi chú không được vượt quá {max} ký tự.
~~~

Spring Boot tự tìm `messages*.properties` cho UI khi auto-configure `MessageSource`; Jakarta Bean Validation sử dụng những key `{form....}` để resolve thông báo từ resource bundles tương ứng. `{max}` được validator nội suy từ thuộc tính `@Size(max=...)`. Khi kiểm thử i18n, hãy xác minh **cả label và lỗi** ở locale mong muốn. Không nên gộp bí mật, user input hoặc HTML chưa được escape vào message bundles.

### 6.9. form.html: view nhập liệu, switch locale, hiển thị lỗi

**src/main/resources/templates/form.html**:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title th:text="#{form.title}">Registration form</title>
</head>
<body>
  <nav>
    <span th:text="#{form.language}">Language</span>:
    <a th:href="@{/form(lang='en')}">English</a>
    <a th:href="@{/form(lang='vi')}">Tiếng Việt</a>
  </nav>

  <h1 th:text="#{form.title}">Registration form</h1>

  <p th:if="${saved}" th:text="#{form.saved}">
    Draft saved.
  </p>

  <form th:action="@{/form}" th:object="${draft}" method="post">
    <div>
      <label for="name" th:text="#{form.name}">Name</label>
      <input id="name" type="text" th:field="*{name}" maxlength="80">
      <span th:if="${#fields.hasErrors('name')}"
            th:errors="*{name}">Name error</span>
    </div>

    <div>
      <label for="email" th:text="#{form.email}">Email</label>
      <input id="email" type="email" th:field="*{email}">
      <span th:if="${#fields.hasErrors('email')}"
            th:errors="*{email}">Email error</span>
    </div>

    <div>
      <label for="note" th:text="#{form.note}">Notes</label>
      <textarea id="note" th:field="*{note}" maxlength="200"></textarea>
      <span th:if="${#fields.hasErrors('note')}"
            th:errors="*{note}">Notes error</span>
    </div>

    <button type="submit" name="action" value="save"
            th:text="#{form.save}">Save draft</button>
    <button type="submit" name="action" value="finish"
            th:text="#{form.finish}">Submit</button>
  </form>
</body>
</html>
~~~

`th:field` tạo/điền giá trị input từ `RegistrationDraft`; sau lỗi, nó được render lại cùng `BindingResult`. Trên browser thật, `type="email"` có client-side validation mặc định; để **kiểm thử riêng server-side validation**, MockMvc/cURL có thể gửi form data không hợp lệ trực tiếp. Trong production, nên bổ sung `aria-describedby`, liên kết lỗi với input, CSS error state, keyboard focus và hỗ trợ screen reader.

Không dùng `th:utext` với dữ liệu của người dùng. `th:text` thực hiện escaping HTML; trang kết quả dùng cùng nguyên tắc để tránh XSS.

### 6.10. done.html: view GET sau redirect

**src/main/resources/templates/done.html**:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title th:text="#{form.done.title}">Completed</title>
</head>
<body>
  <h1 th:text="#{form.done.title}">Completed</h1>
  <p>
    <span th:text="#{form.done.message}">Received for:</span>
    <strong th:text="${completedName}">Visitor</strong>
  </p>
  <a th:href="@{/form}" th:text="#{form.new}">New registration</a>
</body>
</html>
~~~

Trong demo, `completedName` là flash attribute tồn tại cho GET đích sau redirect. Dòng hiển thị bằng `th:text` giúp escape ký tự như `<`, `>` trong input. Nếu cần hiển thị lâu dài kết quả thực tế, lưu record vào database và thiết kế `GET /registrations/{id}` có authorization thích hợp.

## 7. Kiểm thử workflow bằng Spring Boot + MockMvc

MockMvc chạy HTTP request giả trong MVC stack, dùng thực controllers, view resolver, binder, validator, interceptor và session của ứng dụng. Có thể assert view name, status, Location, flash attributes, field errors và HTML đã render. Test này **không mở socket TCP**, không chứng minh reverse proxy/TLS; muốn test browser thực, dùng Selenium/Playwright hoặc test client HTTP tới RANDOM_PORT bổ sung.

**src/test/java/demo/FormFlowTest.java**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class FormFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getFormRendersThymeleafView() throws Exception {
        mvc.perform(get("/form"))
            .andExpect(status().isOk())
            .andExpect(view().name("form"))
            .andExpect(model().attributeExists("draft"))
            .andExpect(content().string(containsString("Registration form")));
    }

    @Test
    void languageChoicePersistsWithinOneHttpSession() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(get("/form").session(session).param("lang", "vi"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("Biểu mẫu đăng ký")));

        mvc.perform(get("/form").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("Biểu mẫu đăng ký")));
    }

    @Test
    void saveDraftRedirectsAndKeepsFormDataInSession() throws Exception {
        MockHttpSession session = new MockHttpSession();
        mvc.perform(get("/form").session(session))
            .andExpect(status().isOk());

        mvc.perform(post("/form").session(session)
                .param("action", "save")
                .param("name", "Lan")
                .param("email", "lan@example.org")
                .param("note", "Gọi vào buổi sáng"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/form"))
            .andExpect(flash().attribute("saved", true));

        RegistrationDraft draft =
            (RegistrationDraft) session.getAttribute("draft");
        assertEquals("Lan", draft.getName());
        assertEquals("lan@example.org", draft.getEmail());

        mvc.perform(get("/form").session(session))
            .andExpect(status().isOk())
            .andExpect(model().attributeExists("draft"))
            .andExpect(content().string(containsString("Lan")));
    }

    @Test
    void invalidFinalSubmitReturnsSameViewWithFieldErrors()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/form").session(session)
                .param("action", "finish")
                .param("name", " ")
                .param("email", "not-an-email")
                .param("note", ""))
            .andExpect(status().isOk())
            .andExpect(view().name("form"))
            .andExpect(model().attributeHasFieldErrors(
                "draft", "name", "email"));

        // Invalid form chưa gọi SessionStatus.setComplete().
        RegistrationDraft draft =
            (RegistrationDraft) session.getAttribute("draft");
        assertEquals("not-an-email", draft.getEmail());
    }

    @Test
    void validFinalSubmitUsesPrgAndClearsDraft() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(get("/form").session(session))
            .andExpect(status().isOk());

        MvcResult result = mvc.perform(post("/form").session(session)
                .param("action", "finish")
                .param("name", "Lan")
                .param("email", "lan@example.org")
                .param("note", ""))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/done"))
            .andExpect(flash().attribute("completedName", "Lan"))
            .andReturn();

        assertNull(session.getAttribute("draft"));

        mvc.perform(get("/done").session(session)
                .flashAttrs(result.getFlashMap()))
            .andExpect(status().isOk())
            .andExpect(view().name("done"))
            .andExpect(content().string(containsString("Lan")));
    }

    @Test
    void directDoneUrlWithoutFlashRedirectsToForm() throws Exception {
        mvc.perform(get("/done"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/form"));
    }
}
~~~

Có **6 phương thức `@Test`**: render view; đổi locale và duy trì qua session; lưu draft và redirect; validation thất bại; PRG thành công và xóa draft; truy cập trực tiếp trang done bị redirect. Những assertions kiểm tra cả HTML render và lifecycle, không chỉ gọi trực tiếp method controller.

Giải thích hai điểm dễ nhầm khi test:

- Dùng cùng `MockHttpSession` cho nhiều `mvc.perform(...)` để mô phỏng browser mang cùng session cookie. Mỗi `MockHttpSession` mới đại diện một phiên khác; nếu dùng session khác ở GET sau POST thì draft/locale **không còn** là điều đúng.
- `MvcResult.getFlashMap()` lấy flash data của POST và `.flashAttrs(...)` gắn nó vào GET mô phỏng sau redirect. MockMvc không tự chạy browser follow redirect; test phải chủ động thực hiện GET tiếp theo. Trong browser thật, `RedirectAttributes`/FlashMap của Spring xử lý lưu và tiêu thụ flash qua redirect.

Để chạy test:

~~~bash
mvn -q test
~~~

Nếu mọi test pass, Maven trả exit code **0**, báo cáo nằm trong `target/surefire-reports/`. Chế độ `-q` có thể không in dòng tóm tắt; không nhầm “không có output” với đã kiểm chứng thành công nếu chưa xem exit code. Đây là ví dụ hoàn chỉnh để thực hành; kết quả runtime **không được khẳng định là đã chạy trong lúc biên soạn bài**.

## 8. Chạy web app và quan sát các request

Khởi động project từ thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Nếu cổng 8080 trống và không có cấu hình khác, truy cập:

~~~text
http://localhost:8080/form
http://localhost:8080/form?lang=vi
http://localhost:8080/form?lang=en
~~~

Kịch bản thao tác:
1. Mở `/form?lang=vi`, kiểm nhãn **Biểu mẫu đăng ký** và **Lưu bản nháp**.
2. Nhập tên `Lan`, email `lan@example.org`, ghi chú tùy ý, bấm **Lưu bản nháp**. Quan sát DevTools Network: **POST /form → HTTP redirect → GET /form**; dữ liệu còn trên form.
3. Sửa email thành sai định dạng và bấm **Gửi đăng ký**. Trình duyệt có thể chặn submit tại client do input type=email; để chủ động kiểm server, dùng cURL/MockMvc hoặc DevTools thay đổi thuộc tính `type` thành text. Server sẽ trả lại view với lỗi.
4. Sửa email hợp lệ rồi gửi. Trình duyệt nhận redirect sang `/done`, hiện thông báo tên vừa nhập. Refresh ở URL kết quả không gửi lại POST.
5. Quay về `/form`: draft cũ đã được `SessionStatus.setComplete()` xóa nên object mới bắt đầu trống; lựa chọn `lang=vi` vẫn được giữ trong cùng HTTP session.

Nếu dùng cURL để tái hiện qua nhiều request, cần giữ cookie:

~~~bash
curl -c cookies.txt -b cookies.txt -i \
  "http://localhost:8080/form?lang=vi"

curl -c cookies.txt -b cookies.txt -i \
  -X POST "http://localhost:8080/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "action=save" \
  --data-urlencode "name=Lan" \
  --data-urlencode "email=lan@example.org" \
  --data-urlencode "note=Ghi chú"

curl -c cookies.txt -b cookies.txt -i \
  "http://localhost:8080/form"
~~~

File `cookies.txt` ở đây là **file do cURL tạo trên máy người học**, không phải file cấu hình Spring. Không commit cookie/token vào Git hoặc đăng tải trong bug report. Nếu bật Spring Security cho app, POST sẽ cần CSRF token hợp lệ và có thể yêu cầu authentication; các lệnh cURL demo lúc đó phải bổ sung quy trình bảo mật thích hợp.

## 9. Các điểm cần hiểu rõ trước khi chuyển demo sang production

### 9.1. Session lifetime và nhiều tab

Trong ứng dụng demo, một phiên browser có đúng một `draft` theo tên attribute. Hai tab cùng browser có thể dùng chung JSESSIONID, sửa cùng draft và gây tình trạng tab A ghi đè tab B. Để hỗ trợ nhiều form song song, thêm workflow ID duy nhất, scope trạng thái theo ID và kiểm soát concurrency.

Session không phải database vĩnh viễn: restart server, timeout, failover hoặc người dùng xóa cookie có thể làm mất draft. Nếu người dùng kỳ vọng có bản nháp lưu nhiều ngày/đa thiết bị, lưu DB với định danh tài khoản, quyền truy cập và lịch sử phiên bản; session chỉ giữ tham chiếu nhẹ.

Trong cluster, session có thể được lưu trong shared backing store như Redis qua Spring Session hoặc routing theo session affinity. Các object được đưa vào distributed session cần xem xét serialization, schema evolution, dung lượng, TTL và dữ liệu nhạy cảm. Không đặt mật khẩu, số thẻ hay dữ liệu nhạy cảm không cần thiết trong session.

### 9.2. CSRF, XSS và phân quyền

`POST /form` là state-changing action. Trong ứng dụng có đăng nhập/cookie, dùng Spring Security CSRF protection theo cấu hình; form Thymeleaf thường tích hợp hidden CSRF field khi Spring Security/RequestDataValueProcessor được cấu hình đúng, nhưng phải test response và submit thực. Không tự tắt CSRF để ví dụ chạy nếu môi trường production cần nó.

`th:text` và `th:field` hỗ trợ escaping HTML, nhưng mọi nội dung từ input vẫn phải được validate/sanitize phù hợp mục đích hiển thị. Không dùng `th:utext` cho nội dung chưa tin cậy. Session cookie nên có `HttpOnly`, `Secure` khi HTTPS, `SameSite` phù hợp, session timeout và session fixation protection theo security policy.

PRG giải quyết UX refresh, không phải bảo vệ khỏi POST trùng hay CSRF. Một action gửi đăng ký thực sự cần server-side uniqueness/idempotency và authorization riêng.

### 9.3. Form binding và mass assignment

Input `RegistrationDraft` chỉ chứa field mà browser được phép gửi. Nếu dùng JPA entity trực tiếp với `id`, `role`, `isAdmin`, `verified`, attacker có thể gửi thêm form parameters để sửa thuộc tính không xuất hiện trên UI. Vì vậy dùng DTO, chuyển sang entity trong service và thêm allowed fields/constructor binding khi cần.

Đối với chức năng **save draft** không validate đầy đủ, vẫn cần giới hạn request size, lengths, số phiên và tần suất để tránh abuse. Trong ứng dụng có nghiệp vụ quan trọng, save draft có thể validate một số invariant tối thiểu khác với validation hoàn tất.

### 9.4. URL redirect và dữ liệu nhạy cảm

`redirect:/done` là server-controlled relative URL. Không lấy tham số `next` do user đưa vào rồi `redirect:` tùy ý: đó có thể tạo **open redirect**. Nếu cần “quay lại trang trước”, dùng allowlist host/path đã kiểm tra.

`RedirectAttributes.addFlashAttribute` không đưa dữ liệu vào URL theo mặc định, nhưng không phải kho bí mật lâu dài: flash thường được giữ trong session và có thể bị request đồng thời tiêu thụ trước dự kiến. Tránh dùng flash để chuyển dữ liệu tài chính/credential, và không coi GET trang hoàn tất là nguồn sự thật nghiệp vụ.

### 9.5. Bản địa hóa thực tế

Trong production cần quyết định:
- Ngôn ngữ nào được hỗ trợ và cách fallback nếu thiếu message key.
- Việc lựa chọn ngôn ngữ được lưu trong session, cookie, tài khoản hay URL.
- Validation messages, ngày/giờ, số, đơn vị tiền tệ, plural forms có tuân locale không.
- Accessibility của language switch; có cần cập nhật `lang` attribute của thẻ `<html>` theo locale hiện tại không.
- Không chỉ kiểm nhãn form; error messages, email, trang thành công cũng cần kiểm vi/en.

Bản ví dụ đặt `<html lang="en">` tĩnh để giữ HTML đơn giản; với trang song ngữ thực tế nên bind thuộc tính lang theo locale (chẳng hạn `th:lang="${#locale.language}"`) để screen reader phát âm đúng. Cần test locale selector và `Accept-Language` trên môi trường thực, nhất là khi proxy/CDN cache HTML.

## 10. Ma trận kiểm thử cần có

| Tình huống | Kỳ vọng | Lớp test |
| --- | --- | --- |
| GET form mới | 200, view form, model draft mới | MockMvc |
| Switch `?lang=vi` | Label tiếng Việt và session ghi locale | MockMvc nhiều request cùng session |
| GET tiếp không có lang | Vẫn giữ tiếng Việt | MockMvc |
| POST save draft thiếu field | Redirect /form; draft vẫn lưu | MockMvc |
| GET sau save | Giá trị name/email/note còn trên form | MockMvc với MockHttpSession |
| POST finish với blank name | View form, field error name, không xóa draft | MockMvc |
| POST finish với email sai | View form, error email | MockMvc |
| POST finish hợp lệ | Redirect /done, flash completedName, draft bị xóa | MockMvc |
| GET /done sau redirect | View done và tên được escape | MockMvc/browser |
| GET /done trực tiếp | Redirect /form khi không có flash | MockMvc |
| Session mới | Locale/draft không rò từ session cũ | MockMvc dùng hai sessions |
| Session timeout | Draft mất theo contract, không có 500 | Integration |
| Two tabs cùng session | Xem rủi ro overwrite, quyết định workflow ID | Browser/integration |
| Security enabled | POST có CSRF hợp lệ; token sai bị từ chối | spring-security-test/integration |
| Reverse proxy | Cookie/redirect Location/scheme đúng qua HTTPS | E2E qua proxy |
| Double POST | Side effects không trùng theo idempotency contract | Service/integration |

Nếu muốn test HTML escaping, gửi tên chứa ký tự `<`/`>` qua luồng hợp lệ rồi kiểm output là escaped text, không chứa HTML/script được thực thi. Với mock HTML, tránh so sánh nguyên cả tài liệu vì whitespace/layout có thể thay đổi; kiểm đoạn text, view name, status và model quan trọng.

## 11. Những lỗi phổ biến và cách khắc phục

1. **Đặt form.html trong `static` thay vì `templates`:** Spring không tìm được logical view `form` bằng Thymeleaf. Đặt đúng `src/main/resources/templates/`.
2. **Dùng `@RestController` cho trang HTML:** trả string `"form"` như response body thay vì view name. Dùng `@Controller`.
3. **Thiếu `th:object` nhưng dùng `th:field="*{...}"`:** binding template lỗi. Đảm bảo model có object đúng tên.
4. **Quên `@Valid`/`spring-boot-starter-validation`:** các annotation DTO không được thực thi như dự tính. Test input sai phải có field errors.
5. **Đặt `BindingResult` không ngay sau form object:** không bắt lỗi binding/validation đúng. Sửa signature của handler.
6. **Redirect sau validation lỗi:** mất field errors hoặc form values nếu không lưu riêng. Return logical view `form` trong request lỗi.
7. **Dùng `AcceptHeaderLocaleResolver` với `LocaleChangeInterceptor`:** resolver này không hỗ trợ thay locale qua setLocale. Chọn SessionLocaleResolver/CookieLocaleResolver hoặc cơ chế thiết kế khác.
8. **Chỉ tạo `messages_vi.properties` mà quên bundle mặc định:** thiếu fallback và các key của ngôn ngữ khác; dùng bundle chuẩn mặc định.
9. **Hardcode UI text trong HTML/Java:** đổi ngôn ngữ chỉ hoạt động một phần. Dùng `#{key}` và resource bundles nhất quán.
10. **Nhầm flash với session state:** flash sống qua một redirect; draft cần session/workflow state qua nhiều request.
11. **Gọi `HttpSession.invalidate()` khi hoàn tất form:** có thể làm mất đăng nhập/locale. Dùng `SessionStatus.setComplete()` để xóa thuộc tính workflow do controller quản lý.
12. **Quên dọn draft sau submit:** lần đăng ký sau thấy dữ liệu cũ; gọi setComplete khi nghiệp vụ đã hoàn tất thật.
13. **Giả định PRG chống duplicate submit:** hai POST vẫn có thể chạy; cần idempotency/unique operation key khi có side effects.
14. **Lưu dữ liệu quá lớn/nhạy cảm trong session:** tốn bộ nhớ, tạo rủi ro bảo mật và vấn đề replication.
15. **Không test cùng session cookie:** GET sau POST mất draft, locale không được giữ, dễ kết luận sai cấu hình. Sử dụng cùng MockHttpSession/cookie.
16. **So sánh raw HTML nguyên trang:** test dễ vỡ theo format; kiểm contract (status, view, text/key elements/redirect/flash).
17. **Redirect từ input không kiểm tra:** có thể tạo open redirect. Chỉ cho phép URL nội bộ/allowlist.
18. **Dựa vào flash để xem lại đăng ký vĩnh viễn:** refresh/direct link không đủ dữ liệu; trang kết quả production phải đọc dữ liệu đã lưu có authorization.
19. **Không xử lý nhiều tab:** một draft theo session có thể bị ghi đè; thiết kế ID hoặc optimistic locking khi cần.
20. **Chỉ thử browser có client-side validation:** không chứng minh Bean Validation phía server. Dùng MockMvc/cURL gửi input vi phạm.

## 12. Checklist triển khai

Với một trang biểu mẫu Spring MVC hoàn chỉnh, hãy kiểm lần lượt:
1. Route GET/POST và logical view names đúng; template Thymeleaf đọc model object đã khai báo.
2. Dữ liệu được bind bằng DTO riêng, ràng buộc `@Valid` và `BindingResult` chạy trên server, field errors render đúng.
3. Labels, buttons, thông báo validation và done page có resource bundles; locale được chọn và duy trì đúng vòng đời.
4. Session state chỉ lưu điều cần thiết, có thời hạn và được xóa bằng `SessionStatus.setComplete()` sau thành công.
5. Redirect sau POST thành công, flash được tiêu thụ đúng; POST lỗi render lại form cùng dữ liệu và thông báo.
6. Security CSRF/XSS/authorization, kích thước request, session cookie và dữ liệu nhạy cảm có chính sách rõ.
7. MockMvc và integration tests xác minh happy path, invalid input, cùng/new session, redirect, flash, localization, timeout và double-submit theo rủi ro.
8. Nếu production nhiều instance, xác minh session storage/affinity, reverse proxy forwarded headers và redirect dưới HTTPS.

## 13. Kết luận

**View** hiển thị form và phản hồi cho người dùng; **binding/validation** chuyển request vào DTO an toàn; **bản địa hóa** chọn message theo locale; **session** lưu trạng thái bản nháp qua nhiều request; **redirect + flash** giúp hoàn tất POST theo PRG mà không mất thông báo nhất thời.

Những phần đó chỉ thật sự gắn kết khi được kiểm thử trong cùng một HTTP workflow. Với Spring MVC, thiết kế tách `FormController` và `DoneController`, `@SessionAttributes`, `SessionLocaleResolver`, `RedirectAttributes` và các test MockMvc cho phép kiểm tra rõ từng trách nhiệm. Khi chuyển sang ứng dụng thật, bổ sung persistence, security, concurrency và idempotency thay vì mở rộng session thành database.

## Tài liệu tham khảo

- Spring Framework — MVC view technologies và Thymeleaf: https://docs.spring.io/spring-framework/reference/web/webmvc-view.html
- Spring Framework — ModelAttribute / Data Binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — @SessionAttributes: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html
- Spring Framework — Locale và SessionLocaleResolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html
- Spring Framework — RedirectAttributes và Flash Attributes: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html
- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html
- Thymeleaf — Spring form binding and validation: https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
- Spring Boot 3.3 — Testing: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html

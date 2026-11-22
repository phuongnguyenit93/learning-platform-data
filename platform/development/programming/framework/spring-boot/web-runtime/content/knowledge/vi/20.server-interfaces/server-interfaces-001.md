# @Controller, Model và tên view trong ứng dụng web

Trong Spring Boot, một ứng dụng **server-side rendering (SSR)** có thể dựng HTML trên máy chủ rồi gửi kết quả cho browser. Ba thành phần thường phối hợp là **`@Controller`** (nhận request, gọi nghiệp vụ và chọn kết quả), **`Model`** (dữ liệu trình bày của request) và **tên view** (tên logic để tìm template). Nếu controller trả `"products/list"`, Spring MVC có thể tìm `src/main/resources/templates/products/list.html`, render với Thymeleaf và trả HTML.

**Phân biệt ngay từ đầu:** trong phương thức thuộc `@Controller` thông thường, `return "home"` chọn view tên `home`, không gửi chữ `home`. Nếu handler gắn `@ResponseBody` hoặc nằm trong `@RestController`, chuỗi trả về được ghi thành HTTP response body. Bài học dùng **Spring Boot 3.x, Spring MVC, Thymeleaf và Java 17+**.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

- Mô tả luồng `DispatcherServlet` → `@Controller` → `Model` → `ViewResolver` → template → HTML.
- Viết handler trả tên view, thêm dữ liệu bằng `Model.addAttribute` và đặt đúng template.
- Phân biệt tên view, URL mapping, đường dẫn file và HTTP response body.
- Dùng `@ModelAttribute`, form DTO, `@Valid` và `BindingResult` với form HTML.
- Giải thích `redirect:`, `forward:`, Post/Redirect/Get (PRG) và flash attributes.
- Tránh các lỗi thường gặp: template missing, model key mismatch, mass assignment, XSS và state mutable trên controller.
- Chạy dự án Java 17+ có ba trang HTML, validation và endpoint trả body để tự đối chiếu.

## 2. Luồng xử lý một trang HTML

```text
Browser: GET /?name=Lan
   |
   v
Servlet container / Embedded Tomcat
   |
   v
DispatcherServlet
   |
   +--> HandlerMapping tìm @GetMapping("/")
   +--> HandlerAdapter gọi PageController.index(...)
   |       |
   |       +--> model.addAttribute("name", "Lan")
   |       +--> return "index"
   |
   +--> ViewResolver giải view name "index"
   |       |
   |       +--> ThymeleafView
   |       +--> templates/index.html + Model
   v
HTTP 200, Content-Type: text/html
   |
   v
Browser hiển thị "Xin chào, Lan!"
```

`DispatcherServlet` là front controller của Spring MVC. `HandlerMapping` tìm handler phù hợp URL/HTTP method, `HandlerAdapter` hỗ trợ gọi handler với các tham số như `Model`, `@RequestParam`, `@ModelAttribute`. Nếu handler trả một `String` như tên view, `ViewResolver` tìm đối tượng `View` tương ứng, template engine trộn Model vào HTML. Đó là luồng HTML truyền thống; handler trả JSON, file, redirect hoặc xử lý async có thể đi theo nhánh khác.

| Thành phần | Vai trò | Điều dễ nhầm |
| --- | --- | --- |
| `@Controller` | Bean nhận request, chọn view hoặc kiểu kết quả khác | Không đồng nghĩa với `@RestController` |
| `@GetMapping`/`@PostMapping` | Định nghĩa URL + HTTP method | Không quyết định file template |
| `Model` | Các key/value cung cấp cho render | Không phải database hoặc HTTP session |
| `String` trả từ handler MVC HTML | Tên view logic | Không phải text body khi không có `@ResponseBody` |
| `ViewResolver` | Tìm view dựa trên logical name | Không định tuyến HTTP request |
| Thymeleaf | Render template thành HTML | Không thay thế business service |
| `redirect:` | Gửi HTTP redirect sang URL | Không render template ở handler hiện tại |

## 3. @Controller, @RestController và @ResponseBody

`@Controller` là stereotype được Spring component scanning nhận diện. Các phương thức gắn `@RequestMapping`, `@GetMapping`, `@PostMapping`… có thể xử lý HTTP request.

Snippet cho một trang HTML:

```java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class WelcomeController {
    @GetMapping("/welcome")
    public String welcome(Model model) {
        model.addAttribute("message", "Xin chào Spring MVC");
        return "welcome";
    }
}
```

Đây là **snippet**, cần ứng dụng Spring Boot và template `src/main/resources/templates/welcome.html`. Nó nhận `GET /welcome`, thêm `message`, rồi chọn view `welcome`. Nó không tự trả body `welcome`.

Trong khi đó:

```java
@Controller
class PageController {
    @GetMapping("/page")
    public String page() {
        return "home"; // Chọn view home
    }

    @GetMapping("/plain")
    @ResponseBody
    public String plain() {
        return "OK"; // Response body là OK
    }
}

@RestController
class ApiController {
    @GetMapping("/api/status")
    public String status() {
        return "OK"; // Response body là OK
    }
}
```

Đây là **snippet so sánh**, cần import các annotations tương ứng và template `home` cho route `/page`. `@RestController` kết hợp hiệu lực `@Controller` và `@ResponseBody` ở mức lớp. Khi trả DTO qua `@RestController`, Spring thường dùng message converter phù hợp để serialize JSON; với một `String`, giá trị được ghi vào body. Không chuyển controller HTML thành `@RestController` rồi mong `return "home"` vẫn render template.

**Ranh giới thiết kế:** Controller nên nhận input, gọi service, đưa kết quả trình bày vào Model và chọn view/redirect. Không đặt toàn bộ nghiệp vụ, SQL hoặc mutable state theo request trong controller. Bean controller thường là singleton và có thể nhận các request đồng thời.

## 4. Model: dữ liệu dành cho một lượt render

`org.springframework.ui.Model` là giao diện cho các thuộc tính được template truy cập. Spring MVC cấp Model thích hợp khi handler khai báo tham số `Model`:

```java
@GetMapping("/books")
public String books(Model model) {
    model.addAttribute("pageTitle", "Danh sách sách");
    model.addAttribute("count", 3);
    model.addAttribute("books", bookService.findVisibleBooks());
    return "books/list";
}
```

Đây là **snippet**, với `bookService`/view giả định. Trong Thymeleaf:

```html
<h1 th:text="${pageTitle}">Tiêu đề</h1>
<p th:text="|Có ${count} quyển sách|">Số sách</p>
<ul>
  <li th:each="book : ${books}" th:text="${book.title}">
    Tên sách
  </li>
</ul>
```

Các key phải **khớp tên**: `addAttribute("books", ...)` đi với `${books}`, không tự biến thành `${items}`. Nếu Model thiếu key, expression có thể trả trống hoặc báo lỗi tùy cách template truy cập.

### 4.1. Model không lưu dữ liệu bền vững

- **Model:** tập dữ liệu phục vụ view của request hiện tại.
- **Form DTO / View DTO:** object được đặt vào Model, không đồng nghĩa entity.
- **Session/flash:** dữ liệu đi qua nhiều request theo cơ chế riêng.
- **Database entity/repository:** nguồn lưu trữ bền vững, không được thay bằng `Model.addAttribute`.

Sau `redirect:`, browser tạo request mới và Model mặc định của request trước không còn nguyên như cũ. Muốn thông báo một lần sau redirect, dùng `RedirectAttributes.addFlashAttribute`; muốn nội dung có thể tra cứu lại, lưu tại service/repository rồi GET bằng ID.

### 4.2. ModelAndView, ModelMap và Map

Bên cạnh `Model`, Spring MVC chấp nhận `ModelMap` hoặc `Map<String, Object>` làm tham số; `ModelAndView` gộp dữ liệu và view name vào một object:

```java
@GetMapping("/summary")
public String summary(Model model) {
    model.addAttribute("title", "Tổng quan");
    return "summary";
}

@GetMapping("/summary-alt")
public ModelAndView summaryAlt() {
    ModelAndView page = new ModelAndView("summary");
    page.addObject("title", "Tổng quan");
    return page;
}
```

Hai method là **snippets** cần `ModelAndView` và template `summary.html`. Hai cách có cùng kết quả ý nghĩa. `Model` + tên view thường ngắn gọn; `ModelAndView` tiện khi muốn đóng gói view, Model và tùy chọn HTTP status.

## 5. Tên view: khác URL và khác path của file

Với Spring Boot 3.x có starter Thymeleaf, cấu hình mặc định tương đương:

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
```

Tức là:

| Handler trả | File template tương ứng | URL có thể là |
| --- | --- | --- |
| `"index"` | `src/main/resources/templates/index.html` | `/` |
| `"orders/list"` | `src/main/resources/templates/orders/list.html` | `/orders` |
| `"users/edit"` | `src/main/resources/templates/users/edit.html` | `/settings` |
| `"redirect:/orders"` | Không render template tại handler đó | Client chuyển sang `/orders` |
| `"forward:/internal"` | Server chuyển dispatch nội bộ | Browser thường giữ URL |

Không nên trả `"index.html"` nếu suffix đã là `.html`; cũng không trả `src/main/resources/templates/index.html` làm view name. `ViewResolver` nhận **logical view name**, không nhận một file path tùy ý. Với FreeMarker hoặc engine khác, cấu hình có thể khác; kiểm tra đúng `ViewResolver` đang dùng.

**Template** ở `src/main/resources/templates` thường được xử lý qua controller. **Static resources** như `src/main/resources/static/main.css` hoặc `static/logo.svg` được phục vụ như tài nguyên tĩnh, không phải view Thymeleaf. Lệnh `return "index"` không phải request tới `/templates/index.html`.

### 5.1. Triệu chứng không tìm thấy view

Nếu ứng dụng đã match handler nhưng lỗi ở bước render, kiểm tra:

1. Có `spring-boot-starter-thymeleaf` chưa?
2. File đúng `templates/index.html` hay thực tế là `templates/home.html`?
3. Có sai chữ hoa/chữ thường giữa `Index.html` và `index.html` trên Linux không?
4. Có sửa `spring.thymeleaf.prefix`/`suffix` khiến resolver tìm khác path không?
5. Template có được đóng gói vào JAR không?
6. Template có expression truy cập thuộc tính thiếu trong Model không?

Một lỗi render có thể dẫn tới HTTP 500 với template exception, trong khi thiếu URL mapping thường là 404. Đừng quy mọi lỗi “trang không hiển thị” về cùng một nguyên nhân.

## 6. Thymeleaf nhận dữ liệu từ Model ra sao?

Một số biểu thức/thuộc tính:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `${attribute}` | Biểu thức truy cập biến trong Model/context |
| `th:text="${title}"` | Đưa text vào element, escape HTML |
| `th:each="x : ${items}"` | Lặp collection |
| `th:if="${visible}"` | Render có điều kiện |
| `th:unless="${visible}"` | Render nếu điều kiện không đúng |
| `th:href="@{/orders}"` | Sinh link theo context path |
| `th:action="@{/submit}"` | Sinh URL action cho form |
| `th:object="${form}"` | Chọn form object |
| `th:field="*{name}"` | Liên kết input với field `name` |
| `th:errors="*{name}"` | Hiển thị lỗi field từ validation |

`th:text` escape HTML theo mặc định. Ví dụ giá trị Model là `<script>alert(1)</script>` thì được trình bày như text, không sinh thẻ script thực thi. `th:utext` cho phép HTML không escape; không dùng nó với input không đáng tin. Khi xây URL, JavaScript hoặc CSS, cần escaping đúng ngữ cảnh, cùng kiểm tra phân quyền/CSRF riêng.

## 7. @ModelAttribute: hai vai trò

**Cung cấp dữ liệu Model chung:** method có `@ModelAttribute` trả object làm một Model attribute:

```java
@ModelAttribute("siteName")
public String siteName() {
    return "Cổng học Java";
}
```

Đây là snippet trong một `@Controller`, cần import `ModelAttribute`. Mặc dù method trả `String`, nó **không** đặt view name vì được khai báo là phương thức tạo attribute. Có thể dùng `@ControllerAdvice` để cung cấp dữ liệu chung cho nhiều controller trong phạm vi phù hợp; tránh query database nặng trên mọi request chỉ để dựng header.

**Nhận form:** `@ModelAttribute("profileForm")` trên tham số handler bind request params vào object:

```java
@PostMapping("/profile")
public String submit(
        @Valid @ModelAttribute("profileForm") ProfileForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "profile-form";
    }
    return "redirect:/profiles";
}
```

Đây là snippet với `ProfileForm` và template giả định. `BindingResult` phải theo **ngay sau** tham số được bind/validate để handler có thể xem lỗi; nếu thiếu hoặc sai vị trí, validation có thể bị xử lý qua exception thay vì đi vào `result.hasErrors()`. Với lỗi nên render lại form trong request hiện tại để giữ giá trị và lỗi field.

## 8. Dự án Spring MVC + Thymeleaf hoàn chỉnh, Java 17+

Demo có:

- `GET /?name=Mai`: trang HTML có lời chào và danh sách.
- `GET /hello-form`: form nhập tên.
- `POST /hello-form`: validation; lỗi render lại form, hợp lệ redirect sang `/done`.
- `GET /done`: nhận thông báo flash sau redirect.
- `GET /ping`: body văn bản `pong` để so sánh với tên view.

### 8.1. Khởi tạo bằng Spring Initializr

Chọn **Java 17+**, **Spring Boot 3.x** (ví dụ nhánh 3.3.x), Gradle/Groovy, dependencies **Spring Web**, **Thymeleaf** và **Validation**. Với `build.gradle` mà Initializr tạo, khối dependencies cốt lõi:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là **khối dependencies**, không phải toàn bộ file `build.gradle` độc lập; cần Boot plugin, Java plugin, repositories và Gradle Wrapper được Initializr tạo. Không tự đặt version từng starter vì Boot quản lý dependency versions. Spring Boot 4.x có thể dùng tên starter khác, nên nếu tạo dự án 4.x phải đối chiếu tài liệu của major version đó.

Tạo các file:

```text
src/main/
  java/demo/
    MvcViewsApplication.java
    GreetingForm.java
    PageController.java
  resources/templates/
    index.html
    hello-form.html
    done.html
```

### 8.2. MvcViewsApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcViewsApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcViewsApplication.class, args);
    }
}
```

Đặt file tại `src/main/java/demo/MvcViewsApplication.java`. `@SpringBootApplication` ở package `demo` để component scan phát hiện controller cùng package.

### 8.3. GreetingForm.java

```java
package demo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class GreetingForm {

    @NotBlank(message = "Vui lòng nhập tên")
    @Size(max = 60, message = "Tên không được vượt quá 60 ký tự")
    private String name;

    public GreetingForm() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

File `src/main/java/demo/GreetingForm.java` là form DTO; `@NotBlank` kiểm tra tên không trống/không chỉ là whitespace, `@Size` giới hạn độ dài. Các ràng buộc được provider của `spring-boot-starter-validation` thực thi. Thuộc tính HTML `maxlength` chỉ hỗ trợ UX; phía server vẫn phải validate.

### 8.4. PageController.java

```java
package demo;

import java.util.List;
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
public class PageController {

    @GetMapping("/")
    public String index(
            @RequestParam(defaultValue = "Bạn") String name,
            Model model) {

        model.addAttribute("name", name);
        model.addAttribute(
                "topics", List.of("Controller", "Model", "View"));
        return "index";
    }

    @GetMapping("/hello-form")
    public String showForm(Model model) {
        model.addAttribute("greetingForm", new GreetingForm());
        return "hello-form";
    }

    @PostMapping("/hello-form")
    public String submit(
            @Valid @ModelAttribute("greetingForm") GreetingForm form,
            BindingResult errors,
            RedirectAttributes redirectAttributes) {

        if (errors.hasErrors()) {
            return "hello-form";
        }

        redirectAttributes.addFlashAttribute(
                "successMessage",
                "Đã gửi lời chào đến " + form.getName().strip());
        return "redirect:/done";
    }

    @GetMapping("/done")
    public String done() {
        return "done";
    }

    @GetMapping("/ping")
    @ResponseBody
    public String ping() {
        return "pong";
    }
}
```

Đặt ở `src/main/java/demo/PageController.java`. Phân tích:

1. `index` thêm `name` và `topics` vào Model, `return "index"` chọn template.
2. `showForm` tạo object dưới key `greetingForm`, đúng tên mà form template tham chiếu.
3. `submit` bind dữ liệu từ request vào DTO, `@Valid` gọi validation, `BindingResult` nhận lỗi.
4. Nếu có lỗi, `return "hello-form"` trong request hiện tại để giữ thông tin lỗi và input.
5. Nếu hợp lệ, `addFlashAttribute` giữ thông báo một lần cho request đích; `redirect:/done` tạo một HTTP redirect.
6. `done` trả template, framework đưa flash message vào Model của request đích.
7. `ping` trả text body vì `@ResponseBody`, không tìm `ping.html`.

Không cần tạo bean `ViewResolver` riêng khi starter Thymeleaf và Boot auto-configuration đã thiết lập đúng.

### 8.5. index.html

File `src/main/resources/templates/index.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Trang chủ</title>
</head>
<body>
    <h1 th:text="|Xin chào, ${name}!|">Xin chào!</h1>
    <h2>Ba thành phần chính</h2>
    <ul>
        <li th:each="topic : ${topics}"
            th:text="${topic}">Chủ đề</li>
    </ul>
    <a th:href="@{/hello-form}">Mở biểu mẫu</a>
</body>
</html>
```

`th:text` lấy dữ liệu từ Model và escape text; `th:each` lặp `topics`. Phần text trong HTML là fallback khi mở file tĩnh; khi server render, biểu thức Thymeleaf quyết định nội dung xuất ra.

### 8.6. hello-form.html

File `src/main/resources/templates/hello-form.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Biểu mẫu lời chào</title>
</head>
<body>
    <h1>Nhập tên</h1>

    <form method="post"
          th:action="@{/hello-form}"
          th:object="${greetingForm}">

        <label for="name">Tên</label>
        <input id="name" type="text"
               th:field="*{name}" maxlength="60">

        <p th:if="${#fields.hasErrors('name')}"
           th:errors="*{name}">Thông báo lỗi</p>

        <button type="submit">Gửi</button>
    </form>

    <a th:href="@{/}">Trang chủ</a>
</body>
</html>
```

`th:object="${greetingForm}"` khớp Model attribute và `@ModelAttribute("greetingForm")`. `th:field="*{name}"` bind input vào property của form DTO, giữ giá trị người dùng khi validation lỗi. `th:errors` hiển thị message từ Jakarta Validation. Nếu thêm Spring Security và CSRF protection, form POST cần phát token hợp lệ theo cấu hình Spring MVC/Thymeleaf của dự án; ví dụ tối giản này không thêm security starter.

### 8.7. done.html

File `src/main/resources/templates/done.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Hoàn tất</title>
</head>
<body>
    <h1>Hoàn tất biểu mẫu</h1>

    <p th:if="${successMessage != null}"
       th:text="${successMessage}">Đã gửi thành công</p>

    <p th:unless="${successMessage != null}">
        Không có thông báo mới. Hãy gửi biểu mẫu.
    </p>

    <a th:href="@{/hello-form}">Trở lại form</a>
</body>
</html>
```

Khi truy cập `/done` sau redirect thành công, Model có flash attribute `successMessage`; nếu truy cập trực tiếp không có flash, đoạn dự phòng xuất hiện. Flash attributes không được dùng làm kho lưu hồ sơ hoặc dữ liệu giao dịch dài hạn.

## 9. Chạy và kiểm chứng HTTP

Trong thư mục gốc dự án có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Ứng dụng mặc định chạy cổng 8080 nếu không thay `server.port`. Với Spring dependencies, `javac PageController.java` đơn lẻ không có classpath sẽ không biên dịch; dùng Gradle Wrapper để tải dependency, compile và chạy.

### 9.1. Trang GET

```bash
curl -s 'http://localhost:8080/?name=Mai'
```

Trong HTML response, phần nội dung có thể như sau:

```html
<h1>Xin chào, Mai!</h1>
<ul>
    <li>Controller</li>
    <li>Model</li>
    <li>View</li>
</ul>
```

Đây là **fragment minh họa sau render**; response đầy đủ chứa cả HTML head/body và whitespace theo template.

### 9.2. POST với dữ liệu sai

```bash
curl -i -d 'name=' http://localhost:8080/hello-form
```

`@NotBlank` phát lỗi; handler trả view `hello-form` trong cùng request, thông thường HTTP 200 mặc định; HTML có `Vui lòng nhập tên`. Có thể thiết kế status khác theo yêu cầu ứng dụng nhưng không nên redirect khi cần giữ `BindingResult` lỗi trong cùng request.

### 9.3. POST đúng, rồi redirect

```bash
curl -i -d 'name=Lan' http://localhost:8080/hello-form
```

Response thông thường HTTP `302 Found` với `Location: /done` (hoặc URL tương đương theo context path). Browser sau đó GET `/done`. Dùng `curl` với cookie jar để theo redirect và giữ flash:

```bash
curl -s -L -c cookies.txt -b cookies.txt \
  -d 'name=Lan' http://localhost:8080/hello-form
```

HTML trang đích chứa `Đã gửi lời chào đến Lan`. PowerShell có thể gọi `curl.exe` và viết các tham số trên cùng một dòng. App demo **không ghi database**; submit chỉ minh họa flow web.

### 9.4. Text trực tiếp qua @ResponseBody

```bash
curl -s http://localhost:8080/ping
```

Response body chính xác:

```text
pong
```

Không cần tạo template `pong.html`.

## 10. Redirect, forward và PRG

- `return "hello-form"`: render view trong request hiện tại, giữ validation errors và Model.
- `return "redirect:/done"`: phản hồi redirect 3xx, browser thực hiện request mới, Model request trước không tự tồn tại nguyên vẹn.
- `return "forward:/internal"`: chuyển xử lý nội bộ phía server tới URL/handler khác, browser thường giữ nguyên URL, không có redirect round-trip.

**Post/Redirect/Get (PRG)** phù hợp khi một POST đã xử lý thành công và muốn tránh browser hỏi gửi lại form lúc refresh. PRG giảm nguy cơ gửi lại POST do refresh, **không** thay thế idempotency key, transaction hay chống gửi trùng cho thanh toán và thao tác có side effect.

### 10.1. RedirectAttributes và flash

```java
redirectAttributes.addAttribute("id", 42);
// Thuộc tính có thể được đưa vào URL redirect như query parameter.

redirectAttributes.addFlashAttribute("notice", "Đã lưu");
// Thông báo ngắn cho request tiếp theo sau redirect.
```

Đây là **snippet** trong handler có tham số `RedirectAttributes redirectAttributes`. Không đặt thông tin nhạy cảm trên URL; flash thường được quản lý trong session và chỉ nhằm chuyển dữ liệu ngắn, không là nơi lưu object lớn. Khi cần trang chi tiết dữ liệu, redirect bằng ID hợp lệ rồi lấy lại từ service/repository.

### 10.2. Model thường không đồng nghĩa flash

Phản ví dụ nếu muốn message chỉ có trong request redirect đích:

```java
model.addAttribute("message", "Đã lưu");
return "redirect:/done"; // Không nên dựa vào Model thường để làm flash
```

Một số scalar model attributes có thể được đưa thành query parameters tùy cấu hình redirect; không suy rằng toàn bộ Model được chuyển sang request mới. Dùng `RedirectAttributes` tường minh.

## 11. Những lỗi form và template dễ mắc

### 11.1. Key của Model và tên form không khớp

Nếu controller có `model.addAttribute("userForm", new UserForm())` thì template dùng `th:object="${userForm}"`, không dùng `${profileForm}`. Với POST handler, `@ModelAttribute("userForm")` phải dùng cùng tên. Sai tên có thể khiến form field không bind hoặc view báo thiếu form-backing object.

### 11.2. BindingResult đặt sai

Tham số `BindingResult` cho một form object cần nằm ngay sau object đó:

```java
public String submit(
        @Valid @ModelAttribute("userForm") UserForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "users/form";
    }
    return "redirect:/users";
}
```

Đây là **snippet** (chưa có mapping, class và DTO đầy đủ). Nếu thiếu `@Valid` hoặc provider validation, các annotation như `@NotBlank` có thể không được chạy. Nếu `BindingResult` bị đặt ở vị trí sai, exception validation có thể xảy ra thay vì controller xử lý lỗi.

### 11.3. Bind thẳng entity nhạy cảm

Không nhận trực tiếp entity có `isAdmin`, `role`, `price` hoặc thuộc tính người dùng không được sửa từ form. Client có thể gửi thêm parameter ngoài những input đang thấy trong HTML (*mass assignment*). Hãy dùng DTO chỉ gồm field cho phép, validate và ánh xạ vào domain trong service. Ẩn input ở frontend không phải kiểm soát quyền.

### 11.4. Sử dụng state mutable trên singleton Controller

Phản ví dụ:

```java
private String currentName;

@GetMapping("/hello")
public String hello(@RequestParam String name) {
    currentName = name; // Request này có thể ghi đè request khác
    return "hello";
}
```

Snippet trên không có Model và lưu tên vào field dùng chung. Controller thường singleton, nên race condition hoặc lộ dữ liệu giữa user có thể xảy ra. Giữ dữ liệu per-request trong local variables/Model, và state cần lưu dài hạn phải có cơ chế riêng.

### 11.5. View name lấy trực tiếp từ input không đáng tin

```java
@GetMapping("/preview")
public String preview(@RequestParam String template) {
    return template; // Không có whitelist
}
```

Đây là **phản ví dụ**: người dùng không nên tùy ý chọn view hoặc các prefix đặc biệt `redirect:`/`forward:`. Ánh xạ lựa chọn vào danh sách view hợp lệ và kiểm tra quyền.

## 12. Bảo mật và hiệu năng khi render giao diện

**XSS:** dùng `th:text` để escape text, không đưa nội dung user vào `th:utext` không qua xử lý. Với giá trị đưa vào URL/JavaScript/HTML attribute, dùng cách tạo biểu thức an toàn đúng ngữ cảnh, không ghép string HTML trực tiếp ở controller.

**CSRF:** khi app có xác thực qua cookie/session, các form POST đổi trạng thái cần cơ chế CSRF thích hợp. Tích hợp Spring Security phải bảo đảm token có mặt và hợp lệ khi gửi form. Không coi demo tối giản chưa bật security là cấu hình production hoàn chỉnh.

**Authorization:** template ẩn một nút không ngăn người dùng gửi request trực tiếp. Controller và service vẫn phải kiểm tra quyền truy cập/sửa dữ liệu.

**Chỉ truyền dữ liệu cần hiển thị:** query danh sách lớn rồi đưa tất cả vào Model khiến request tốn RAM và render chậm. Dùng view DTO, phân trang, cache dữ liệu tham chiếu và tránh gọi repository hoặc xử lý nghiệp vụ phức tạp trực tiếp trong template.

**Template caching:** trong môi trường dev có thể dùng:

```properties
spring.thymeleaf.cache=false
```

Trong production, cân nhắc giữ cache để giảm parse template lặp lại. Không in secret hay toàn bộ Model nhạy cảm ra log chỉ để debug view.

**URL theo context path:** nên dùng `th:href="@{/...}"` và `th:action="@{/...}"` để Spring/Thymeleaf sinh link phù hợp ứng dụng. Hardcode đường dẫn cứng có thể lỗi khi deploy dưới context path khác.

## 13. Chẩn đoán nhanh

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Browser hiện chữ `index` | Handler có `@ResponseBody`/`@RestController` | Dùng `@Controller` khi trả logical view |
| 404 | Không có mapping phù hợp | Kiểm tra `@GetMapping`, HTTP method, context path |
| Template not found | Sai view name, file hoặc starter | Kiểm tra `templates` và Thymeleaf resolver |
| HTML thiếu dữ liệu | Model key khác expression | Đối chiếu `addAttribute` và `${...}` |
| Form hiển thị lỗi template | Thiếu object `greetingForm` | Khởi tạo form và khớp `th:object` |
| Validation không báo lỗi | Thiếu `@Valid`/starter/`BindingResult` | Kiểm tra dependency và chữ ký handler |
| Lỗi biến mất sau redirect | Không còn request Model/BindingResult | Render lại form nếu invalid |
| Refresh hỏi gửi lại POST | Trả view ngay sau submit đúng | Dùng PRG: redirect sang GET |
| Flash không hiện bằng curl | Không theo redirect/cookie | Dùng `curl -L -c -b` |
| XSS | Render raw HTML không tin cậy | Dùng escape và validate context |
| Trang chậm khi nhiều records | Query/Model/template quá nặng | Pagination và view DTO |
| Cùng dữ liệu xuất hiện giữa user | Mutable controller field | Dữ liệu local/Model theo request |

Để phân biệt lỗi, xem `curl -i` hoặc Browser Network: status 404 liên quan route, HTTP 3xx có header `Location`, còn template exception xảy ra sau khi handler trả tên view. Theo dõi log Spring MVC và Thymeleaf đúng điểm.

## 14. Bài tập tự kiểm tra

**1.** `@Controller` trả `"orders/list"`. Thymeleaf mặc định tìm template nào?  
**Đáp án:** `src/main/resources/templates/orders/list.html`; URL do request mapping quyết định.

**2.** `@RestController` trả `"home"` thì HTML có được render không?  
**Đáp án:** Không, thường response body là chữ `home`.

**3.** Model key là `items` nhưng template dùng `${products}`. Có tự nối không?  
**Đáp án:** Không. Cần thống nhất key và expression.

**4.** Người dùng submit form trống, DTO có `@NotBlank`. Cần gì để hiện lỗi?  
**Đáp án:** `@Valid @ModelAttribute`, `BindingResult` ngay phía sau, nhánh `hasErrors()` trả form, template dùng `th:errors`.

**5.** Tại sao POST đúng thường trả `redirect:`?  
**Đáp án:** Tạo GET sau POST (PRG) để refresh không gửi lại POST một cách vô ý.

**6.** `Model.addAttribute("notice","OK")` xong redirect có chắc là flash không?  
**Đáp án:** Không; dùng `RedirectAttributes.addFlashAttribute` cho thông báo cần hiển thị ở request redirect đích.

**7.** Tại sao không bind thẳng `User` chứa `isAdmin` từ form?  
**Đáp án:** Dễ bị mass assignment; dùng form DTO giới hạn field và authorization ở service.

**8.** Vì sao `th:text` an toàn hơn `th:utext` với tên người dùng?  
**Đáp án:** `th:text` escape HTML, tránh dữ liệu untrusted trở thành thẻ HTML có thể thực thi.

## 15. Checklist triển khai

- [ ] Chọn `@Controller` cho SSR, `@ResponseBody`/`@RestController` cho body trực tiếp.
- [ ] URL mapping và logical view name có chủ đích, không suy từ tên file.
- [ ] Template nằm đúng folder theo prefix/suffix của engine.
- [ ] Model key khớp Thymeleaf expression.
- [ ] Model chỉ chứa dữ liệu cần render, không chứa secret hoặc collection khổng lồ.
- [ ] Form dùng DTO được phép bind, getter/setter và validation phía server.
- [ ] `BindingResult` đặt ngay sau `@Valid @ModelAttribute`.
- [ ] Nhánh lỗi trả lại form để giữ field errors.
- [ ] Nhánh submit thành công dùng PRG và flash khi phù hợp.
- [ ] Không dùng controller singleton field để lưu state theo request.
- [ ] Output người dùng được escape đúng ngữ cảnh, CSRF và quyền truy cập được kiểm soát.
- [ ] Test GET HTML, POST lỗi, POST đúng, redirect, flash và body của `@ResponseBody`.

## Tài liệu chính thức

- [Spring Framework — MVC Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html)
- [Spring Framework — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Redirect Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html)
- [Spring Boot 3.3 — Servlet Web Applications & Template Engines](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Thymeleaf — Tutorial: Thymeleaf + Spring](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html)

Với trang HTML được render ở máy chủ, hãy giữ rõ hợp đồng: **`@Controller` nhận request và quyết định điều hướng, `Model` mang dữ liệu cho lượt render, còn tên view chỉ ra template để `ViewResolver` tìm và tạo HTML**. Tách bạch ba vai trò này giúp sửa lỗi nhanh, kiểm thử tốt và tránh nhầm SSR với REST API.

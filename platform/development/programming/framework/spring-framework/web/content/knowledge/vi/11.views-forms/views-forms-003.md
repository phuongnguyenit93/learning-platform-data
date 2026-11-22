# Thymeleaf, FreeMarker, JSP: vai trò và điều kiện sử dụng trong Spring MVC

> **Phạm vi:** Spring Web MVC trên Servlet stack, Java 17+ và Spring Boot 3.x / Spring Framework 6.x. Chủ đề giải thích vai trò của ba công nghệ view phía server, cách ánh xạ controller → Model → ViewResolver → template, điều kiện dùng từng công nghệ, đường dẫn và dependency, form binding, HTML escaping, giới hạn JSP khi triển khai, cùng ví dụ Java chạy được. Những snippet độc lập được đánh dấu rõ ràng.

## 1. View nằm ở đâu trong Spring MVC?

Khi xây dựng trang web render từ server, controller nhận HTTP request, chuẩn bị dữ liệu trong **Model** rồi trả về **logical view name**. `ViewResolver` tìm View phù hợp; View engine ghép model và template để tạo HTML.

```text
GET /hello?name=Lan
        |
DispatcherServlet
        |
@Controller + Model
        | model.addAttribute("name", "Lan")
        | return "hello"
        v
ViewResolver
        | Thymeleaf: templates/hello.html
        | FreeMarker: templates/hello.ftlh
        | JSP: /WEB-INF/jsp/hello.jsp
        v
Rendered HTML --> Browser
```

Controller minh họa:

```java
@Controller
class GreetingController {
    @GetMapping("/hello")
    String hello(
            @RequestParam(defaultValue = "Guest") String name,
            Model model) {
        model.addAttribute("name", name);
        return "hello";
    }
}
```

Các import ở ví dụ: `org.springframework.stereotype.Controller`, `org.springframework.web.bind.annotation.GetMapping`, `RequestParam`, `org.springframework.ui.Model`.

**Chú ý:** `return "hello"` trong `@Controller` thường biểu thị **tên view**. Nếu class là `@RestController` (hoặc method có `@ResponseBody`), chuỗi `"hello"` thường chính là **HTTP response body**, được xử lý bởi `HttpMessageConverter`. Khi viết REST API trả JSON/DTO, bạn không nhất thiết phải cài bất kỳ template engine nào.

## 2. Bản đồ lựa chọn nhanh

| Tiêu chí | Thymeleaf | FreeMarker | JSP |
| --- | --- | --- | --- |
| Bản chất | Java HTML template engine, nhấn mạnh natural templates | Java template engine cho HTML/text, có directive và macro | Jakarta Server Pages do servlet container biên dịch thành servlet |
| Cú pháp | `th:text`, `th:each`, `th:object`, `th:field` | `${...}`, `<#if>`, `<#list>`, `<#macro>` | JSP EL `${...}`, JSTL `<c:...>`, Spring taglibs |
| Starter/engine | `spring-boot-starter-thymeleaf` | `spring-boot-starter-freemarker` | JSP compiler + Jakarta JSTL và container |
| Template mặc định trong Boot 3.5 | `classpath:/templates/*.html` | `classpath:/templates/*.ftlh` | Cấu hình view resolver, thường `/WEB-INF/jsp/*.jsp` |
| Thế mạnh | HTML đọc tự nhiên, Spring MVC forms và errors | Template macro, cấu trúc trình bày và output text/HTML | Duy trì ứng dụng Servlet/JSP/JSTL có sẵn |
| Lưu ý triển khai | Template phải hiện diện trên classpath | Chọn đúng HTML output format và escaping | Executable JAR không hỗ trợ JSP; WAR/container yêu cầu riêng |

Ba engine đều làm công việc **render view**, không thay thế controller, business service, database, validation hoặc security. Với một ứng dụng mới đóng gói executable JAR, Thymeleaf hoặc FreeMarker thường dễ triển khai hơn JSP vì JSP có ràng buộc runtime/packaging.

## 3. Thymeleaf: natural HTML và tích hợp Spring form

### 3.1. Khi nào dùng?

Thymeleaf phù hợp khi giao diện chủ yếu HTML phía server, có biểu mẫu Spring MVC, lỗi validation, danh sách hoặc các fragment dùng lại. HTML template vẫn có cấu trúc hợp lệ khi mở trực tiếp để xem trước; thuộc tính `th:*` được engine xử lý khi server render.

Với Spring Boot 3.x, khai báo:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-thymeleaf</artifactId>
</dependency>
```

Đây là fragment của `pom.xml` dùng Spring Boot parent/BOM; với ứng dụng servlet thêm `spring-boot-starter-web`. Các giá trị mặc định của Spring Boot 3.5:

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.mode=HTML
spring.thymeleaf.encoding=UTF-8
```

Không cần viết những dòng này nếu dùng đúng mặc định. `return "hello"` sẽ được resolver ánh xạ tới `src/main/resources/templates/hello.html`.

### 3.2. Ví dụ HTML

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Xin chào</title>
</head>
<body>
  <h1 th:text="'Xin chào, ' + ${name}">Xin chào, khách</h1>
  <a th:href="@{/hello(name='Mai')}">Chào Mai</a>
</body>
</html>
```

- `${name}` lấy thuộc tính `name` từ model.
- `th:text` ghi nội dung **HTML-escaped** vào phần tử.
- `@{...}` là URL expression, tạo URL đúng hơn so với hardcode trong trường hợp ứng dụng có context path.
- Text HTML gốc `Xin chào, khách` là bản preview; khi render, engine thay nội dung bằng giá trị model.

Nếu client truyền `name=<script>alert(1)</script>`, `th:text` render nó như ký tự text đã escape, chứ không phải thẻ script. Tránh dùng `th:utext` với HTML không đáng tin cậy vì nó có thể đưa markup do người dùng kiểm soát vào DOM.

### 3.3. Lặp, điều kiện, fragments

```html
<ul>
  <li th:each="book : ${books}"
      th:text="${book}">Sách mẫu</li>
</ul>
<p th:if="${books.empty}">Chưa có sách</p>
```

Controller cần đặt model attribute `books` tương ứng. Để tái sử dụng đoạn giao diện:

```html
<!-- templates/fragments/common.html -->
<footer th:fragment="footer">Ví dụ Spring MVC</footer>
```

```html
<!-- trong template khác -->
<div th:replace="~{fragments/common :: footer}"></div>
```

### 3.4. Spring form binding

```html
<form th:action="@{/profiles}" th:object="${profileForm}" method="post">
  <label>Tên
    <input type="text" th:field="*{displayName}">
  </label>
  <p th:if="${#fields.hasErrors('displayName')}"
     th:errors="*{displayName}">Lỗi tên</p>
  <button type="submit">Lưu</button>
</form>
```

Trong controller, GET đặt `profileForm` vào model, còn POST khai báo `@Valid @ModelAttribute("profileForm") ProfileForm form` với `BindingResult` đứng **ngay sau** form object. Các helper `th:field`, `th:errors` dựa trên binding/validation infrastructure của Spring MVC.

Nếu dùng Spring Security với CSRF enabled, POST form cần CSRF token. Thymeleaf có tích hợp giúp sinh token trong những điều kiện phù hợp, nhưng luôn kiểm tra HTML thực sự render và security config. Không coi UI field hidden/disabled là bảo mật: client vẫn có thể tạo request tự do.

## 4. FreeMarker: directive, macro và template đa dụng

### 4.1. Khi nào dùng?

FreeMarker phù hợp khi hệ thống có nhiều template/macro, nhu cầu lặp/điều kiện phức tạp ở tầng trình bày, hoặc đã sử dụng FreeMarker cho HTML và các loại văn bản khác. Nó là template engine, không phải servlet container/JSP.

Dependency với Spring Boot 3.x:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-freemarker</artifactId>
</dependency>
```

Spring Boot 3.5 mặc định:

```properties
spring.freemarker.template-loader-path=classpath:/templates/
spring.freemarker.suffix=.ftlh
spring.freemarker.charset=UTF-8
spring.freemarker.content-type=text/html
```

Đặc biệt, **suffix mặc định là `.ftlh`** trong Boot 3.5, không phải `.ftl` như nhiều tutorial cũ. `return "hello"` trỏ tới `src/main/resources/templates/hello.ftlh`.

### 4.2. HTML template

```html
<!doctype html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Xin chào</title></head>
<body>
  <h1>Xin chào, ${name}!</h1>
  <#if books?has_content>
    <ul>
      <#list books as book>
        <li>${book}</li>
      </#list>
    </ul>
  <#else>
    <p>Chưa có sách</p>
  </#if>
</body>
</html>
```

FreeMarker dùng:
- `${name}` để chèn model value;
- `<#if>` / `<#else>` cho điều kiện;
- `<#list books as book>` cho vòng lặp;
- `${name!'Guest'}` đặt default value khi `name` thiếu.

Với template `.ftlh` và HTML output format chuẩn, FreeMarker auto-escape văn bản trong HTML. Không tắt escaping hoặc dùng `?no_esc` cho input không tin cậy. Nếu dùng `.ftl` qua cấu hình legacy, hãy xác minh HTML output format và escaping; đổi filename chưa đủ để bảo đảm XSS safety cho mọi template.

### 4.3. Macro, form và điều kiện thực tế

```ftl
<#macro label value>
  <span class="label">${value}</span>
</#macro>

<@label value="Spring MVC" />
```

Đoạn macro có thể lưu trong template tương ứng rồi import:

```ftl
<#import "macros.ftlh" as ui>
<@ui.label value="Book" />
```

FreeMarker không dùng cú pháp `th:object/th:field`. Form thông thường có HTML `name="displayName"` và model values:

```html
<form action="/profiles" method="post">
  <input type="text" name="displayName" value="${displayName!}">
  <button type="submit">Lưu</button>
</form>
```

Đây chỉ là fragment giao diện; với context path không rỗng, CSRF, validation errors và bảo vệ dữ liệu, cần Spring/FreeMarker macro integration hoặc thêm model/URL handling tương ứng. Đừng copy đoạn trên thành form production chưa xử lý CSRF. Các macro của Spring hỗ trợ binding và thông báo lỗi khi cấu hình/import đúng.

## 5. JSP: view truyền thống thuộc Servlet/Jakarta ecosystem

### 5.1. JSP được render thế nào?

JSP (Jakarta Server Pages) được servlet container dịch thành servlet và thực thi. Trong Spring MVC, controller vẫn trả logical view name; `InternalResourceViewResolver` thường forward tới file JSP. JSP có Expression Language (EL), JSTL tag libraries và Spring JSP form tags.

Mẫu cấu trúc project:

```text
src/main/
├─ java/com/example/demo/DemoApplication.java
└─ webapp/
   └─ WEB-INF/
      └─ jsp/
         └─ hello.jsp
```

Cấu hình view resolver thông thường trong Spring Boot:

```properties
spring.mvc.view.prefix=/WEB-INF/jsp/
spring.mvc.view.suffix=.jsp
```

Vậy `return "hello"` thường forward nội bộ tới `/WEB-INF/jsp/hello.jsp`. Đặt JSP dưới `WEB-INF` giúp ngăn client truy cập trực tiếp JSP theo đường dẫn thông thường; yêu cầu phải qua controller/mapping. Với JSP, `InternalResourceViewResolver` thường cần nằm **cuối chuỗi ViewResolver** vì nó có thể nhận diện tên view rất rộng và ngăn resolver trước/sau hoạt động đúng.

### 5.2. Giới hạn quan trọng khi chạy Spring Boot

Theo hướng dẫn Spring Boot về embedded servlet containers:

- **Executable JAR không hỗ trợ JSP.**
- Với **Tomcat và Jetty**, JSP có thể hoạt động bằng **WAR packaging**; executable WAR có thể chạy với `java -jar application.war` và WAR có thể deploy vào container ngoài tương thích.
- **Undertow không hỗ trợ JSP.**
- Custom `error.jsp` không mặc định thay đổi error view của Spring Boot; cần error page setup riêng.
- Đường dẫn `src/main/webapp`, build plugin, JSP engine và version Jakarta phải phù hợp. Không đặt JSP ở `classpath:/templates` rồi kỳ vọng boot JAR render như Thymeleaf.

Ví dụ dependency WAR/Tomcat/JSP cho **Spring Boot 3.x**:

```xml
<packaging>war</packaging>

<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.apache.tomcat.embed</groupId>
    <artifactId>tomcat-embed-jasper</artifactId>
  </dependency>
  <dependency>
    <groupId>jakarta.servlet.jsp.jstl</groupId>
    <artifactId>jakarta.servlet.jsp.jstl-api</artifactId>
  </dependency>
  <dependency>
    <groupId>org.glassfish.web</groupId>
    <artifactId>jakarta.servlet.jsp.jstl</artifactId>
  </dependency>
</dependencies>
```

Đây là **fragment POM**, không phải `pom.xml` độc lập. Spring Boot BOM/parent cần quản lý các version tương thích. Khi deploy WAR vào container ngoài, thường cấu hình embedded container với scope `provided` theo hướng dẫn Boot; khi chạy executable WAR, cần giữ classpath/package phù hợp. Không dùng dependency `javax.servlet`/JSTL cũ với Spring Boot 3.x (Jakarta namespaces).

Lớp ứng dụng hỗ trợ external WAR deployment:

```java
@SpringBootApplication
public class DemoApplication extends SpringBootServletInitializer {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(DemoApplication.class);
    }
}
```

Đoạn trên yêu cầu các import Spring Boot tương ứng; đây là phần cấu hình WAR minh họa, **không phải chương trình đầy đủ**.

### 5.3. JSP/JSTL template

```jsp
<%@ page contentType="text/html; charset=UTF-8"
         pageEncoding="UTF-8" %>
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<!doctype html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Xin chào JSP</title></head>
<body>
  <h1>Xin chào, <c:out value="${name}" />!</h1>
  <ul>
    <c:forEach items="${books}" var="book">
      <li><c:out value="${book}" /></li>
    </c:forEach>
  </ul>
</body>
</html>
```

- JSP EL `${name}` truy cập model value được expose cho view.
- JSTL `<c:out>` escape ký tự XML/HTML trong vùng text.
- `<c:forEach>` lặp collection trong model.
- URI `jakarta.tags.core` phù hợp Jakarta JSTL hiện đại; taglib `http://java.sun.com/jsp/jstl/core` hay gặp trong ứng dụng Java EE cũ, cần đánh giá/di chuyển khi nâng cấp.
- Spring JSP form tag library có thể hỗ trợ binding/form nhưng cần cấu hình JSTL/Spring tags tương thích, không đồng nhất với Thymeleaf syntax.

### 5.4. Khi nào nên duy trì JSP?

Phù hợp nếu hệ thống hiện có hàng trăm trang JSP, chuẩn deployment WAR và container tương thích, hoặc sử dụng JSTL/Spring JSP taglibs mà chưa có lý do chính đáng để chuyển. Nếu cần một Spring Boot service mới đóng gói executable JAR, Thymeleaf hoặc FreeMarker thường ít hạn chế hơn. Không nên chuyển JSP sang engine khác chỉ bằng đổi extension file: phải chuyển cả cú pháp template, taglibs và form handling.

## 6. ViewResolver, model, static assets và return values

Một controller:

```java
@GetMapping("/catalog")
String catalog(Model model) {
    model.addAttribute("title", "Sách lập trình");
    return "catalog/list";
}
```

Cùng `"catalog/list"` có thể resolve thành:

| Engine | File theo cấu hình phổ biến |
| --- | --- |
| Thymeleaf | `classpath:/templates/catalog/list.html` |
| FreeMarker | `classpath:/templates/catalog/list.ftlh` |
| JSP | `/WEB-INF/jsp/catalog/list.jsp` |

**Phân biệt ba loại output:**

1. **Template HTML:** logical view name được chuyển thành file view và render với Model.
2. **Static asset:** CSS, JavaScript, hình ảnh đặt dưới `src/main/resources/static/` (hoặc vị trí static resources đã cấu hình), phục vụ qua resource handler, không thông qua template expression.
3. **REST response:** body JSON/text thông qua `@RestController`/`@ResponseBody` và `HttpMessageConverter`, không cần ViewResolver.

View resolver order đặc biệt quan trọng nếu đăng ký nhiều engine. Với cùng view name `"hello"` và cả Thymeleaf + FreeMarker starter, có thể có resolver cạnh tranh tùy điều kiện resource và thứ tự. Cách đơn giản là **chọn một template engine chính**; nếu bắt buộc dùng nhiều engine, cấu hình `view-names` pattern và resolver order rõ ràng, test cả trường hợp view tồn tại/không tồn tại.

### 6.1. Redirect và forward

```java
@GetMapping("/old")
String old() {
    return "redirect:/new";
}
```

`"redirect:/new"` gây HTTP redirect; browser gửi một request tiếp theo. `"forward:/internal"` thực hiện forward nội bộ theo quy tắc MVC/Servlet. `return "hello"` thuần là logical view name, không yêu cầu browser gửi request mới. Sau POST thành công, **Post/Redirect/Get** giảm việc form bị submit lại khi refresh.

## 7. Ví dụ chạy được — Spring Boot 3.x + Thymeleaf

Để tránh va chạm `ViewResolver`, ví dụ hoàn chỉnh chọn một engine duy nhất: **Thymeleaf**. Tạo project từ [Spring Initializr](https://start.spring.io/), Java 17+, Maven, dependencies **Spring Web**, **Thymeleaf**, **Validation**. Các thư viện tương ứng:

```xml
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
</dependencies>
```

Đây là fragment của POM. Khi tạo qua Initializr, Maven parent, plugin, versions và project metadata đã được chuẩn bị.

### 7.1. Cấu trúc file

```text
src/main/
├─ java/com/example/demo/DemoApplication.java
└─ resources/
   └─ templates/
      ├─ books.html
      └─ book-form.html
```

### 7.2. Java controller và form bean đầy đủ

Đặt trong `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

class BookForm {
    @NotBlank
    @Size(max = 80)
    private String title = "";

    public BookForm() {
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}

@Controller
class PageController {
    private final List<String> books =
            new CopyOnWriteArrayList<>(List.of("Spring MVC"));

    @GetMapping("/books")
    public String list(Model model) {
        model.addAttribute("books", List.copyOf(books));
        return "books";
    }

    @GetMapping("/books/new")
    public String form(Model model) {
        model.addAttribute("bookForm", new BookForm());
        return "book-form";
    }

    @PostMapping("/books")
    public String create(
            @Valid @ModelAttribute("bookForm") BookForm form,
            BindingResult bindingResult,
            RedirectAttributes redirects) {
        if (bindingResult.hasErrors()) {
            return "book-form";
        }

        books.add(form.getTitle());
        redirects.addFlashAttribute("notice", "Đã thêm sách");
        return "redirect:/books";
    }
}
```

- `PageController` là `@Controller` để trả **view names**.
- GET `/books` đưa danh sách `books` vào Model; GET `/books/new` đưa bean `bookForm` vào Model.
- POST `/books` nhận form theo `@ModelAttribute`; `@Valid` chạy Bean Validation và `BindingResult` phải đứng ngay sau form parameter.
- Nếu title rỗng hoặc vượt 80 ký tự, method trả `"book-form"` để render lại lỗi.
- Khi thành công, thêm sách vào list, set flash message rồi redirect sang GET `/books`. Đây là PRG, không render HTML ngay từ POST.
- Demo dùng in-memory list, không có database/security. Code production cần request DTO chỉ chứa field hợp đồng, CSRF protection (nếu có session authentication), authorization và persistence.

### 7.3. Template hiển thị danh sách

`src/main/resources/templates/books.html`:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Danh sách sách</title>
</head>
<body>
  <h1>Sách đã thêm</h1>
  <p th:if="${notice}" th:text="${notice}"></p>
  <ul>
    <li th:each="book : ${books}"
        th:text="${book}">Sách mẫu</li>
  </ul>
  <a th:href="@{/books/new}">Thêm sách</a>
</body>
</html>
```

Với dữ liệu ban đầu, trang hiển thị mục `Spring MVC`. Sau POST thêm `Effective Java`, request GET tiếp theo hiển thị cả hai mục. Dữ liệu title chứa dấu `<`/`>` được escape bởi `th:text`.

### 7.4. Template biểu mẫu

`src/main/resources/templates/book-form.html`:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Thêm sách</title>
</head>
<body>
  <h1>Thêm sách mới</h1>
  <form th:action="@{/books}" th:object="${bookForm}" method="post">
    <label for="title">Tên sách</label>
    <input id="title" type="text" th:field="*{title}" maxlength="80">
    <p th:if="${#fields.hasErrors('title')}"
       th:errors="*{title}">Tên sách không hợp lệ</p>
    <button type="submit">Lưu</button>
  </form>
  <a th:href="@{/books}">Quay lại</a>
</body>
</html>
```

Client-side `maxlength="80"` chỉ hỗ trợ giao diện; `@Size(max = 80)` phía server vẫn cần. Việc validation và binding hoạt động không đồng nghĩa đã có CSRF/authorization; ví dụ cố ý không cài Spring Security để tập trung vào view.

### 7.5. Chạy và kiểm tra kết quả

Từ root project Maven:

```bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

Mở `http://localhost:8080/books` và `http://localhost:8080/books/new`. Với port mặc định và không có context path tùy chỉnh, cả hai GET trả HTML trang tương ứng (status 200).

Request POST hợp lệ:

```bash
curl -i -X POST 'http://localhost:8080/books' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title=Effective Java'
```

Dự kiến status **302 Found** và header `Location` trỏ đến `/books` (có thể biểu diễn URL theo context path/config). Browser theo redirect, hiển thị list có `Effective Java`. Nếu dùng cURL `-L`, cURL đi theo redirect; đừng giả định response đầu tiên là HTML list.

Request POST title rỗng:

```bash
curl -i -X POST 'http://localhost:8080/books' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'title='
```

Controller render lại `book-form.html` có lỗi validation hiển thị qua `th:errors`. Vì đây là mô hình form truyền thống và method chỉ return view name, status phản hồi trong ví dụ thông thường **200 OK** dù form chưa hợp lệ; API JSON có thể chọn error status khác.

Lệnh trên sử dụng Bash `\` nối dòng. Trong PowerShell, dùng `curl.exe` và đặt toàn bộ câu lệnh trên một dòng.

## 8. Đổi cùng controller sang FreeMarker

Muốn chuyển **engine** mà giữ logic controller, thay `spring-boot-starter-thymeleaf` bằng `spring-boot-starter-freemarker` và đổi templates sang `*.ftlh` với cú pháp FreeMarker. Một file danh sách tối thiểu `src/main/resources/templates/books.ftlh`:

```html
<!doctype html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Danh sách sách</title></head>
<body>
  <h1>Sách đã thêm</h1>
  <#if notice??><p>${notice}</p></#if>
  <ul>
    <#list books as book>
      <li>${book}</li>
    </#list>
  </ul>
  <a href="/books/new">Thêm sách</a>
</body>
</html>
```

Nội dung trên thể hiện data model và list rendering nhưng **chưa phải bản port hoàn chỉnh của form**; cần thêm `book-form.ftlh`, input name `title`, giá trị cũ và validation error model/macro Spring. Tránh giữ nguyên th:object/th:field trong FreeMarker template. Link hardcode `/books/new` hợp lệ ở root context của demo; dự án có context path nên dùng URL helper theo engine/cấu hình.

Khi chỉ có FreeMarker, logical view name `"books"` tìm `books.ftlh` với default Boot 3.5. Nếu dùng file `.ftl`, hãy đặt `spring.freemarker.suffix=.ftl` **và** kiểm tra HTML escaping/output format.

## 9. Đổi sang JSP và triển khai WAR

Với JSP, giữ controller `@Controller` trả `"books"` nhưng thay hướng đóng gói: WAR + JSP engine/JSTL + `/WEB-INF/jsp/`. Đặt:

```properties
spring.mvc.view.prefix=/WEB-INF/jsp/
spring.mvc.view.suffix=.jsp
```

Ví dụ `src/main/webapp/WEB-INF/jsp/books.jsp`:

```jsp
<%@ page contentType="text/html; charset=UTF-8"
         pageEncoding="UTF-8" %>
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<!doctype html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Danh sách sách</title></head>
<body>
  <h1>Sách đã thêm</h1>
  <c:if test="${not empty notice}">
    <p><c:out value="${notice}" /></p>
  </c:if>
  <ul>
    <c:forEach items="${books}" var="book">
      <li><c:out value="${book}" /></li>
    </c:forEach>
  </ul>
  <a href="<c:url value='/books/new' />">Thêm sách</a>
</body>
</html>
```

Để port trọn ứng dụng, còn phải xây `book-form.jsp` với JSP/Spring form tags, validation display, CSRF token và URL helpers. Build/test cần chạy trong Tomcat hoặc Jetty JSP-capable với WAR và version Jakarta đúng. Đừng chạy executable JAR và kỳ vọng `.jsp` sẽ tự hoạt động.

## 10. Bảo mật và ranh giới trách nhiệm của template

| Rủi ro | Cách phòng |
| --- | --- |
| XSS từ input user | Thymeleaf `th:text`, FreeMarker HTML auto-escape, JSP JSTL `c:out`; encode theo đúng context |
| Render template do user tự upload/sửa | Không chạy template không đáng tin cậy trong application context |
| Form POST bị CSRF | CSRF protection với token và xác minh HTML form đã render |
| Mass assignment | Request DTO/allowed fields, validation, explicit entity updates |
| Truy cập trái quyền | Authorization ở controller/service/security, không chỉ ẩn link trong HTML |
| Rò rỉ thuộc tính object | Chỉ đưa dữ liệu cần thiết vào Model, hạn chế model chứa thông tin nhạy cảm |
| URL/path injection | Tạo href/action qua engine URL helper, không nối input tùy ý vào đường dẫn |
| Escape sai ngữ cảnh | Không đưa giá trị chưa kiểm soát vào inline JS, HTML attributes, CSS hoặc raw HTML |
| Template cache | Tắt cache có mục đích trong dev, cân nhắc bật trong production |

**Quan trọng:** HTML escaping trong text context không thay thế CSP và các nguyên tắc an toàn ở URL/JavaScript context. Ví dụ đầu vào `<script>alert(1)</script>` nếu được đưa qua `th:text`, `${value}` trong FreeMarker HTML output format hoặc `<c:out>` trong JSP sẽ được hiển thị như text thay vì tạo script tag. Nhưng `th:utext`, `?no_esc`, raw JSP EL có thể làm mất lớp bảo vệ này.

## 11. Khi nào dùng engine nào trong dự án thật?

**Chọn Thymeleaf** khi bắt đầu một trang MVC mới, cần biểu mẫu tích hợp Spring, templates HTML người thiết kế có thể xem trước và triển khai executable JAR. Chi phí chính: engine cú pháp `th:*` và cách xử lý fragments/form errors.

**Chọn FreeMarker** khi đã có các macro/template phức tạp hoặc cần cùng hệ template cho nhiều loại nội dung; nó vẫn render HTML tốt khi output format và escaping chuẩn. Chi phí chính: cú pháp FreeMarker khác HTML tự nhiên và phải chủ động tích hợp form/validation behavior của MVC.

**Giữ JSP** khi hệ thống legacy có JSP/JSTL assets/tags lớn hoặc mục tiêu deployment là WAR trên servlet container có JSP support. Chi phí chính: điều kiện WAR/container, JSP compiler, JSTL Jakarta compatibility và bảo trì template. Không chọn JSP cho Spring Boot executable JAR.

**Không cần engine nào** nếu service cung cấp REST JSON cho React/Vue/mobile. Controller trả DTO bằng `@RestController` và response được serialize qua `HttpMessageConverter`; đó là một kiến trúc khác với server-rendered views.

## 12. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Điều cần xem | Sửa thế nào |
| --- | --- | --- |
| Trang in chữ `books` thay HTML | Method/class có `@ResponseBody`/`@RestController`? | Dùng `@Controller` cho view |
| Template không tìm thấy | Starter, prefix, suffix, file path | Đặt file đúng `templates/` và tên logical view |
| FreeMarker không đọc file `.ftl` | Boot 3.5 default `.ftlh` | Đổi filename/config và xác minh escaping |
| JSP không render trong executable JAR | JSP packaging không được hỗ trợ | Dùng WAR và container có JSP support |
| JSP taglib không tìm thấy | Thiếu JSTL hoặc taglib URI/version sai | Đồng bộ Jakarta JSTL API+implementation |
| `Circular view path` | View resolver forward trùng request path | Điều chỉnh view name/prefix/suffix |
| Có nhiều engine, trang dùng sai view | Các ViewResolver trùng tên/pattern | Chọn một engine hoặc phân tách view-names/order |
| CSS/JS trả 404 | Nhầm static resource với template | Đặt CSS/JS dưới `static/` và dùng URL đúng |
| Form gửi lỗi 403 | Có thể thiếu/không đúng CSRF token | Kiểm tra Spring Security filter và form HTML |
| Validation không hiện lỗi | Sai tên model attribute, thiếu starter, `BindingResult` sai vị trí | Kiểm tra `@Valid` và binding |
| Trang bị XSS | Raw/unescaped input trong HTML | Escape đúng context và không render template không tin cậy |
| Thêm JSP vẫn lỗi 500 | Container, WAR config, JSP compiler/classpath | Test build WAR và runtime JSP thực tế |

Khi debug, đi theo thứ tự: HTTP mapping → controller return value → ViewResolver → resource path/suffix → engine dependency → runtime packaging → model variables → escaping/security. Với JSP, xác minh **WAR và container** trước khi sửa controller. Với Thymeleaf/FreeMarker, xác minh **starter và classpath templates** trước khi chỉnh ViewResolver.

## 13. Câu hỏi tự kiểm tra

**1.** Method `@RestController` trả `"hello"` nhưng có `templates/hello.html`. Spring sẽ render template không?

**Đáp án:** Không, chuỗi được xử lý như response body. Muốn logical view name, dùng `@Controller` phù hợp.

**2.** Với Boot 3.5 mặc định, `return "list"` trỏ tới file gì trong Thymeleaf và FreeMarker?

**Đáp án:** Thymeleaf `classpath:/templates/list.html`, FreeMarker `classpath:/templates/list.ftlh` nếu các starter/resolver tương ứng được cấu hình.

**3.** Thay `spring-boot-starter-thymeleaf` bằng FreeMarker rồi giữ nguyên `th:field` trong HTML có hoạt động không?

**Đáp án:** Không. Phải chuyển sang FreeMarker template cú pháp thích hợp và xử lý form binding/validation.

**4.** Vì sao Spring Boot executable JAR là dấu hiệu không nên chọn JSP?

**Đáp án:** Theo tài liệu Spring Boot, JSP không được hỗ trợ trong executable JAR; dùng WAR với Tomcat/Jetty JSP-capable nếu cần JSP.

**5.** Đưa chuỗi từ user vào HTML bằng phương thức nào an toàn hơn?

**Đáp án:** Dùng `th:text`, FreeMarker HTML auto-escaping, hoặc `<c:out>` (cho text context), đồng thời encode đúng ngữ cảnh và kiểm soát input.

**6.** `return "redirect:/books"` khác `return "books"` như thế nào?

**Đáp án:** Redirect yêu cầu trình duyệt gửi GET mới; view name render template cho request hiện tại. PRG thường dùng redirect sau POST thành công.

## 14. Tài liệu chuẩn

- [Spring Framework — View Technologies](https://docs.spring.io/spring-framework/reference/web/webmvc-view.html): Spring MVC pluggable view technologies, ranh giới tin cậy template.
- [Spring Framework — View Resolvers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/view-resolvers.html): thứ tự và cấu hình ViewResolver.
- [Spring Framework — Thymeleaf](https://docs.spring.io/spring-framework/reference/web/webmvc-view/mvc-thymeleaf.html): nguyên lý Thymeleaf trong Spring MVC.
- [Spring Framework — FreeMarker](https://docs.spring.io/spring-framework/reference/web/webmvc-view/mvc-freemarker.html): tích hợp FreeMarker, macro và cấu hình.
- [Spring Framework — JSP and JSTL](https://docs.spring.io/spring-framework/reference/web/webmvc-view/mvc-jsp.html): JSP view resolver, JSTL, JSP tags.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): giới hạn JSP cho WAR/JAR và servlet container.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.thymeleaf.*`, `spring.freemarker.*`, `spring.mvc.view.*`.
- [Thymeleaf documentation](https://www.thymeleaf.org/documentation.html): HTML templates, expressions, fragments.
- [Apache FreeMarker Manual](https://freemarker.apache.org/docs/): FreeMarker directives, macros và output escaping.

**Ghi nhớ:** cả ba công nghệ đều đảm nhiệm **View** trong Spring MVC nhưng khác cú pháp, dependency và điều kiện triển khai. Thymeleaf thuận lợi cho HTML/form với Spring, FreeMarker mạnh về template/macro, JSP phù hợp hệ Servlet legacy có WAR và JSP container. Khi triển khai, hãy kiểm tra đúng engine, file path/suffix, logical view names, HTML escaping, validation, CSRF và quyền truy cập thay vì chỉ nhìn vào HTML hiển thị.

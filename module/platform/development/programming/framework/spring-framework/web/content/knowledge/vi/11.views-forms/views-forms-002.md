# ViewResolver, thứ tự phân giải và tích hợp template engine trong Spring MVC

## 1. Bài toán và mục tiêu

Trong Spring MVC, một controller có thể trả về chuỗi `"books/detail"`, nhưng trình duyệt cuối cùng nhận HTML được tạo từ file `templates/books/detail.html`. Ai tìm ra file tương ứng? Tại sao tên view đôi khi chạy qua Thymeleaf, đôi khi lại bị chuyển sang JSP? Cần hiểu **ViewResolver**, **View** và thứ tự phân giải để giải đáp.

Bài học này giúp bạn:

- Phân biệt URL request, logical view name, `Model`, `ViewResolver`, `View` và template engine.
- Theo dõi đường đi từ kết quả của `@Controller` đến HTML được render.
- Hiểu nhiều `ViewResolver` được xét theo thứ tự `order` và vì sao `InternalResourceViewResolver` dành cho JSP phải đặt cuối.
- Phân biệt `BeanNameViewResolver`, `InternalResourceViewResolver`, `ThymeleafViewResolver`, `FreeMarkerViewResolver` và `ContentNegotiatingViewResolver`.
- Cấu hình Thymeleaf theo Spring Boot, dùng prefix/suffix và view names; phân biệt thứ tự MVC ViewResolver với thứ tự template resolver riêng của engine.
- Hiểu `redirect:`, `forward:`, `ModelAndView`, form binding và trường hợp `@RestController` không cần view resolution.
- Chạy ứng dụng Spring Boot 3 + Java 17 với HTML templates, form validation, redirect và test bằng `MockMvc`.

**Phạm vi:** Spring MVC trên Servlet stack, phù hợp Spring Framework 6.x, Spring Boot 3.x và Java 17+. Những class của WebFlux dùng cơ chế reactive khác và không phải trọng tâm bài.

## 2. Logical view name khác HTML, URL và API response

Một controller minh họa:

```java
@Controller
class BookPageController {

    @GetMapping("/books/7")
    String detail(Model model) {
        model.addAttribute("title", "Học Spring MVC");
        return "books/detail";
    }
}
```

*Đoạn minh họa nằm trong class controller có imports phù hợp; ví dụ project đầy đủ ở phần 7.*

Các vai trò:

| Thành phần | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| HTTP URL | `GET /books/7` | Xác định request mà client muốn gửi |
| Handler mapping | `@GetMapping("/books/7")` | Chọn controller method |
| Model | `{"title":"Học Spring MVC"}` | Dữ liệu render cho request hiện tại |
| Logical view name | `"books/detail"` | Tên trừu tượng mà controller trả về |
| ViewResolver | `ThymeleafViewResolver` | Tìm đối tượng View ứng với tên và locale |
| View | Thymeleaf View | Render model bằng template phù hợp |
| Template | `classpath:/templates/books/detail.html` | Nguồn markup/biểu thức được engine xử lý |
| HTTP response | `text/html` | Nội dung HTML trả về cho trình duyệt |

Dữ liệu thường đi theo chuỗi:

```text
HTTP GET /books/7
  → DispatcherServlet
  → HandlerMapping chọn BookPageController.detail
  → HandlerAdapter gọi controller
       ├── Model có thuộc tính title
       └── view name: "books/detail"
  → ViewResolver(s): resolveViewName("books/detail", locale)
       ├── resolver 1 không nhận → null → thử resolver 2
       └── resolver 2 nhận → trả Thymeleaf View
  → View.render(model, request, response)
       ├── đọc/parse template books/detail.html
       ├── áp dụng model + biểu thức template
       └── ghi HTML vào HttpServletResponse
```

**ViewResolver giải quyết tên thành View; View thực sự render.** Controller không cần biết vị trí tuyệt đối của template nếu tên logic và convention đã cấu hình đúng. `ViewResolver` không thay thế `HandlerMapping`: cái thứ nhất hoạt động sau khi controller được chọn, cái thứ hai xác định endpoint HTTP.

### 2.1. Return type có thể bỏ qua bước giải tên view

Trong `@Controller`, một `String` return thông thường là tên view. Trong `@RestController` hoặc method có `@ResponseBody`, `String` lại là body trực tiếp. Ví dụ:

```java
@Controller
class PageController {
    @GetMapping("/home")
    String home() {
        return "home"; // logical view name
    }

    @ResponseBody
    @GetMapping("/plain")
    String plain() {
        return "Hello"; // response body là chuỗi Hello
    }
}

@RestController
class ApiController {
    @GetMapping("/api/hello")
    Map<String, String> hello() {
        return Map.of("message", "Hello"); // Jackson serialize JSON
    }
}
```

*Đây là phần minh họa riêng, cần import `Map` và các annotation khi dùng trong project.* `@RestController` kết hợp `@Controller` với semantics `@ResponseBody`. `ResponseEntity<?>` cũng thường viết thẳng HTTP response qua message converter. Không mong Thymeleaf render `home.html` nếu một `@RestController` trả `"home"`: client thường nhận đúng chữ `home`.

### 2.2. ModelAndView và View object

```java
@GetMapping("/dashboard")
ModelAndView dashboard() {
    return new ModelAndView(
        "dashboard",
        "heading",
        "Trang tổng quan"
    );
}
```

`ModelAndView` chứa view name và model; kết quả tương đương cách truyền `Model` rồi return `"dashboard"`. Cũng có thể cấp trực tiếp một `View` instance, lúc đó không nhất thiết cần resolver tìm theo tên. Trường hợp method không trả view name, MVC đôi khi có thể suy ra tên từ request qua `RequestToViewNameTranslator`, nhưng nên trả tên tường minh để API/controller dễ bảo trì.

## 3. Những ViewResolver thông dụng

| Resolver | Cơ chế | Tình huống thực tế |
| --- | --- | --- |
| `BeanNameViewResolver` | Tìm Spring bean có tên trùng view name và có kiểu `View` | CSV, Excel, PDF hoặc custom View bean |
| `InternalResourceViewResolver` | Thêm prefix/suffix rồi tạo `InternalResourceView` forward/include qua Servlet | JSP/JSTL; **luôn đặt cuối chuỗi** |
| `UrlBasedViewResolver` | Base class ánh xạ tên view sang URL theo convention | Nền tảng cho các resolver dựa trên URL |
| `FreeMarkerViewResolver` | Tạo `FreeMarkerView` cho template tương ứng | Server-side FreeMarker |
| `ThymeleafViewResolver` | Tạo Thymeleaf View, engine xử lý file template | Thymeleaf trong Spring MVC/Boot |
| `ContentNegotiatingViewResolver` | Dựa trên media type/Accept chọn View thích hợp do resolver khác cung cấp | Một resource nhiều dạng trình bày |
| `ViewResolverComposite` | Tập hợp các resolver đã cấu hình | Kết quả cấu hình bằng MVC registry |

Một `ViewResolver` có contract trả `null` nếu không tìm/không phụ trách view name. Khi có nhiều resolver, điều này cho phép phần tử kế tiếp thử. Nhưng không phải resolver nào cũng **biết** template có tồn tại trước khi trả View. Resolver quá tổng quát có thể “chiếm” tên rồi View thất bại ở bước render thay vì nhường cơ hội cho resolver khác.

`AbstractCachingViewResolver` có cơ chế cache các View đã resolve. **Cache View khác cache HTML**: model vẫn có thể khác theo request. Template engine cũng có cache riêng cho nội dung đã parse và HTTP cache/CDN còn là lớp khác nữa.

### 3.1. JSP: InternalResourceViewResolver

Ví dụ:

```java
@Bean
InternalResourceViewResolver jspViewResolver() {
    InternalResourceViewResolver resolver = new InternalResourceViewResolver();
    resolver.setPrefix("/WEB-INF/jsp/");
    resolver.setSuffix(".jsp");
    resolver.setOrder(Ordered.LOWEST_PRECEDENCE);
    return resolver;
}
```

*Đoạn cấu hình minh họa ở ứng dụng JSP riêng; cần import `@Bean`, `Ordered` và `InternalResourceViewResolver`. Không thêm đồng thời vào demo Thymeleaf ở phần 7.*

Tên `"orders/detail"` được ánh xạ thành:

```text
/WEB-INF/jsp/orders/detail.jsp
```

Thường đặt JSP dưới `WEB-INF` để trình duyệt không trực tiếp mở file template. Khi dùng JSTL, cần cấu hình `JstlView` và thư viện JSTL phù hợp. Spring Boot executable JAR thông thường không phải cách triển khai JSP thuận tiện; nếu cần JSP, hãy kiểm tra loại đóng gói WAR/container và các giới hạn JSP của Boot.

### 3.2. BeanNameViewResolver và custom View

Nếu controller return `"monthlyCsv"` và container có bean tên `monthlyCsv` thuộc kiểu `View` thì `BeanNameViewResolver` có thể trả bean đó. Đây là cách ánh xạ trực tiếp tới một View đặc biệt thay vì file template. Một bean service bình thường cùng tên **không** trở thành View.

### 3.3. Thymeleaf và FreeMarker

Với Spring Boot, thêm `spring-boot-starter-thymeleaf` sẽ kích hoạt những cấu hình cần thiết cho Thymeleaf khi điều kiện auto-configuration phù hợp. FreeMarker có starter riêng `spring-boot-starter-freemarker`. Khi chỉ dùng một engine, thường nên để Boot cấu hình mặc định, sau đó chỉnh prefix/suffix/cache qua properties.

Nếu cùng cài nhiều template engines, cần xem **resolver nào thực sự phụ trách từng tên view**. Có thể giới hạn view name patterns và điều chỉnh order để tránh một engine cố render template thuộc engine khác.

## 4. Thứ tự ViewResolver: số nhỏ ưu tiên trước

Spring MVC xem xét nhiều resolver theo `Ordered` và cấu hình thực tế:

- `order = -10` ưu tiên trước `0`.
- `order = 0` ưu tiên trước `10`.
- Resolver có độ ưu tiên thấp hơn (giá trị order lớn hơn) được xét muộn.
- `Ordered.LOWEST_PRECEDENCE` là mức ưu tiên rất thấp, thích hợp cho resolver dự phòng nhận nhiều tên.
- Khi resolver trả `null`, chuỗi có thể tiếp tục; khi nó trả View, kết quả được dùng theo pipeline đã chọn.

Giả sử **cấu hình chủ động**:

| Resolver | Order | View names được nhận |
| --- | ---: | --- |
| `BeanNameViewResolver` | 0 | Chỉ tên có View bean phù hợp |
| `ThymeleafViewResolver` | 10 | `pages/*` |
| `InternalResourceViewResolver` | 1000 | JSP fallback |

Khi controller return `"pages/home"`:

```text
BeanNameViewResolver: không có bean View → null
ThymeleafViewResolver: nhận "pages/home" → Thymeleaf View
InternalResourceViewResolver: không cần chạy
```

Khi return `"legacy/report"`:

```text
BeanNameViewResolver: không có bean → null
ThymeleafViewResolver: không thuộc pages/* → null
InternalResourceViewResolver: /WEB-INF/jsp/legacy/report.jsp
```

Các **con số order trong bảng chỉ là ví dụ**; không phải thứ tự mặc định cố định của mọi phiên bản Spring Boot. Khi debug, phải kiểm tra các bean trong ApplicationContext và cấu hình môi trường thật.

### 4.1. Tại sao JSP resolver bắt buộc cuối chuỗi?

`InternalResourceViewResolver` không thể xác nhận chắc file JSP tồn tại khi mới có view name; thông thường cần thực hiện `RequestDispatcher.forward()` rồi Servlet/JSP container mới xử lý. Do đó resolver này có thể tạo `InternalResourceView` cho hầu hết tên. Nếu nó đứng **trước Thymeleaf**, một tên `"pages/home"` có thể bị đưa tới `/WEB-INF/jsp/pages/home.jsp` dù bạn mong Thymeleaf, khiến trang không render đúng.

**Quy tắc:** đặt `InternalResourceViewResolver` cuối toàn bộ resolver order nếu nhiều ViewResolvers cùng tồn tại. Đây là quy tắc được tài liệu chính thức Spring MVC nhấn mạnh, không chỉ là thói quen cấu hình.

### 4.2. Cấu hình với WebMvcConfigurer

Một ứng dụng Spring MVC **chủ động dùng JSP** có thể cấu hình các resolvers như sau:

```java
@Configuration
class LegacyViewConfig implements WebMvcConfigurer {
    @Override
    public void configureViewResolvers(ViewResolverRegistry registry) {
        registry.beanName();
        registry.jsp("/WEB-INF/jsp/", ".jsp");
    }
}
```

*Đây là đoạn minh họa riêng; cần import `Configuration`, `WebMvcConfigurer`, `ViewResolverRegistry` và môi trường JSP phù hợp. Không chèn vào project Boot/Thymeleaf mẫu.*

`ViewResolverRegistry` còn hỗ trợ đăng ký resolver tùy chỉnh và bật content negotiation khi cần. Trong Spring Boot, **không bật `@EnableWebMvc` chỉ để chỉnh một thuộc tính template**: annotation đó chuyển nhiều phần MVC configuration về bạn và có thể làm mất auto-configuration đang có. Dùng properties và `WebMvcConfigurer` phù hợp trước khi chọn thay thế toàn bộ MVC defaults.

### 4.3. Thứ tự MVC resolver và template resolver là hai chuyện

`ThymeleafViewResolver#setOrder(...)` ảnh hưởng thứ tự **Spring MVC ViewResolver**. Nhưng Thymeleaf còn có các **ITemplateResolver** nội bộ để tìm nguồn template, prefix/suffix và cache. Thuộc tính như `spring.thymeleaf.template-resolver-order` thuộc chuỗi **template resolvers của Thymeleaf**, không sắp xếp các Spring MVC resolvers.

```text
Spring MVC ViewResolver chain
   └── ThymeleafViewResolver
        └── ThymeleafView
             └── Thymeleaf TemplateEngine
                  └── TemplateResolver chain
                       └── classpath:/templates/pages/home.html
```

Nếu view tên `"pages/home"` rơi vào JSP resolver, sửa **MVC ViewResolver order/viewNames**; nếu Thymeleaf đã chọn nhưng tìm sai file, kiểm tra **template prefix/suffix/resource resolution**.

## 5. ContentNegotiatingViewResolver và HTTP Accept

Trong một số ứng dụng, cùng tài nguyên có thể được thể hiện bằng HTML, PDF hoặc JSON:

```http
GET /reports/42 HTTP/1.1
Accept: text/html
```

hoặc:

```http
GET /reports/42 HTTP/1.1
Accept: application/pdf
```

`ContentNegotiatingViewResolver` không tự render HTML/PDF. Nó hỏi các resolver khác lấy candidate `View` rồi chọn View có media type tương thích với nội dung client chấp nhận. Có thể cung cấp thêm `defaultViews` như JSON/PDF View phù hợp. **Không có PDF View thì Accept: application/pdf không tự tạo ra PDF.**

Đường đi phổ biến của REST JSON lại khác:

```text
@RestController trả Java object
 → @ResponseBody return-value handler
 → MappingJackson2HttpMessageConverter
 → application/json response body
```

Trong trường hợp này không bắt buộc có `ContentNegotiatingViewResolver` hoặc `MappingJackson2JsonView`. Phân biệt **content negotiation khi chọn View** với **content negotiation khi chọn HTTP message converter**, dù cả hai đều liên quan đến `Accept`.

Spring Boot có thể tự cấu hình `ContentNegotiatingViewResolver` tùy loại bean `View` và các điều kiện hiện hành. Đừng giả định nó luôn có trong mọi ứng dụng; xem metadata/bean list của context cụ thể.

## 6. Prefix redirect: và forward:

Khi controller trả view name có prefix đặc biệt:

```java
@PostMapping("/save")
String save() {
    return "redirect:/documents/7";
}

@GetMapping("/legacy-entry")
String legacyEntry() {
    return "forward:/internal/page";
}
```

*Đoạn minh họa trong một `@Controller`.*

- `redirect:/documents/7` tạo **redirect HTTP** đến URL mới; browser gửi request mới. Đây là công cụ của Post/Redirect/Get (PRG).
- `forward:/internal/page` yêu cầu **Servlet forward nội bộ** trong cùng request, không phát sinh HTTP redirect cho trình duyệt.
- `redirect:` được các resolver dựa trên URL hỗ trợ như một chỉ thị đặc biệt. Đây không phải tên file HTML.
- `forward:` hữu ích khi cần chuyển đến một URL được Servlet xử lý; không cần dùng để chỉ tới JSP nếu đã cấu hình logical view name qua JSP resolver.

Nếu sau POST hợp lệ cần hiển thị thông báo ở GET tiếp theo, dùng `RedirectAttributes.addFlashAttribute(...)`. Thông tin flash được giữ tạm qua redirect, không nhất thiết xuất hiện trên URL. Nếu form **có lỗi validation**, thường trả lại cùng view trong request hiện tại để giữ input và `BindingResult` thay vì redirect vô điều kiện.

Tránh nối trực tiếp giá trị URL không tin cậy vào `"redirect:" + userInput` vì có thể sinh **open redirect**; whitelist route/host được phép.

## 7. Demo Spring Boot 3 + Thymeleaf + Java 17 hoàn chỉnh

Ứng dụng ví dụ có đủ các đường đi:

- `GET /` → controller trả `"home"`, Thymeleaf render `home.html`.
- `GET /greetings/Ada` → `"greetings/detail"`, HTML dùng `Model`.
- `GET /model-view` → `ModelAndView` trả về cùng template `home`.
- `GET /api/greetings/Ada` → `@RestController` trả JSON, **bỏ qua** view resolution.
- `GET /signup` và `POST /signup` → Thymeleaf form, `@Valid` và `BindingResult`; form hợp lệ redirect tới trang hoàn tất.

Dùng Java 17+, Maven và Spring Boot **3.3.13**. Không cần database hoặc Servlet JSP engine.

### 7.1. Cấu trúc

```text
view-resolution-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/ViewResolutionApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/
    │           ├── home.html
    │           ├── greetings/detail.html
    │           ├── signup.html
    │           └── signup-done.html
    └── test/java/example/ViewResolutionTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>view-resolution-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
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

Thymeleaf starter giúp Boot cấu hình template engine và resolver. Không cần tạo một `ThymeleafViewResolver` bean thủ công để dùng vị trí template mặc định.

### 7.3. application.properties

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.mode=HTML
spring.thymeleaf.encoding=UTF-8
# Tắt cache cho môi trường học tập/development.
spring.thymeleaf.cache=false
```

Những giá trị prefix/suffix trên tương ứng với mặc định của Thymeleaf trong Boot 3.x. Với return `"greetings/detail"`, engine tìm template `classpath:/templates/greetings/detail.html`. Đừng dùng `spring.mvc.view.prefix` để điều chỉnh Thymeleaf; thuộc tính đó phục vụ resolution Servlet resource/JSP ở cấu hình phù hợp.

`spring.thymeleaf.view-names` và `spring.thymeleaf.excluded-view-names` giúp giới hạn nhóm logical names của Thymeleaf khi dùng nhiều engine. Trong production thường nên bật template cache để cải thiện hiệu suất.

### 7.4. ViewResolutionApplication.java

Toàn bộ class/record ở cùng file `src/main/java/example/ViewResolutionApplication.java`; chỉ class main được khai báo `public`.

```java
package example;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.ModelAndView;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@SpringBootApplication
public class ViewResolutionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ViewResolutionApplication.class, args);
    }
}

class SignupForm {
    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    public SignupForm() {}

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
}

@Controller
class PageController {

    @GetMapping("/")
    String home(Model model) {
        model.addAttribute("heading", "Trang chủ MVC");
        return "home";
    }

    @GetMapping("/model-view")
    ModelAndView modelView() {
        return new ModelAndView("home", "heading", "Trang ModelAndView");
    }

    @GetMapping("/greetings/{name}")
    String greeting(@PathVariable String name, Model model) {
        model.addAttribute("message", "Xin chào, " + name + "!");
        return "greetings/detail";
    }

    @GetMapping("/signup")
    String showSignup(Model model) {
        model.addAttribute("signupForm", new SignupForm());
        return "signup";
    }

    @PostMapping("/signup")
    String submit(@Valid @ModelAttribute("signupForm") SignupForm form,
                  BindingResult errors,
                  RedirectAttributes redirectAttributes) {

        if (errors.hasErrors()) {
            return "signup"; // render lại form với BindingResult
        }

        redirectAttributes.addFlashAttribute(
                "notice", "Đã đăng ký: " + form.getName());

        return "redirect:/signup/done";
    }

    @GetMapping("/signup/done")
    String done() {
        return "signup-done";
    }
}

@RestController
class GreetingApiController {
    @GetMapping("/api/greetings/{name}")
    Map<String, String> greeting(@PathVariable String name) {
        return Map.of("message", "Xin chào, " + name + "!");
    }
}
```

Để ý `PageController` và `GreetingApiController` có các đường return khác nhau: String ở `@Controller` là logical view name, trong khi Map ở `@RestController` được viết thẳng thành JSON. `BindingResult` nằm ngay sau form DTO để controller có thể render lại cùng trang khi validation không đạt.

### 7.5. templates/home.html

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Trang chủ</title>
</head>
<body>
  <h1 th:text="${heading}">Tiêu đề mặc định</h1>
  <nav>
    <a th:href="@{/greetings/Ada}">Lời chào</a>
    <a th:href="@{/signup}">Đăng ký</a>
  </nav>
</body>
</html>
```

Thymeleaf dùng `th:text` để đưa model attribute `heading` vào HTML. Cú pháp `${heading}` là một biểu thức Thymeleaf hợp lệ sau khi thay ký hiệu `$` thành dấu dollar `$`; file được tạo ra trong bài này sử dụng đúng dấu `$`.

### 7.6. templates/greetings/detail.html

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Lời chào</title>
</head>
<body>
  <h1 th:text="${message}">Lời chào mặc định</h1>
</body>
</html>
```

`th:text` mặc định escape các ký tự HTML từ model, giúp tránh việc tên người dùng chứa markup được render như HTML. Với dữ liệu không tin cậy, tránh `th:utext` trừ khi đã sanitize theo hợp đồng an toàn.

### 7.7. templates/signup.html

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Đăng ký</title>
</head>
<body>
  <h1>Đăng ký</h1>
  <form th:action="@{/signup}" th:object="${signupForm}" method="post">
    <label>Tên
      <input type="text" th:field="*{name}">
    </label>
    <span th:if="${#fields.hasErrors('name')}"
          th:errors="*{name}">Lỗi tên</span>

    <label>Email
      <input type="email" th:field="*{email}">
    </label>
    <span th:if="${#fields.hasErrors('email')}"
          th:errors="*{email}">Lỗi email</span>

    <button type="submit">Gửi</button>
  </form>
</body>
</html>
```

`th:object` truy cập model attribute `signupForm`. `th:field` liên kết input với property, còn `#fields.hasErrors(...)` và `th:errors` truy cập thông tin validation từ `BindingResult`. Ứng dụng có Spring Security cần tính tới CSRF token theo cấu hình; sample chỉ dùng MVC/Validation.

### 7.8. templates/signup-done.html

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Hoàn tất</title>
</head>
<body>
  <h1>Hoàn tất</h1>
  <p th:text="${notice}">Thông báo</p>
  <a th:href="@{/signup}">Quay lại</a>
</body>
</html>
```

Thông báo `notice` là flash attribute, được lưu tạm qua redirect. Nếu truy cập trực tiếp `/signup/done`, thuộc tính này có thể không tồn tại; ứng dụng thực nên quy định hành vi hiển thị phù hợp.

### 7.9. Chạy ứng dụng

Cần Java 17+ và Maven. Trong thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Dùng browser mở:

```text
http://localhost:8080/
http://localhost:8080/greetings/Ada
http://localhost:8080/signup
http://localhost:8080/api/greetings/Ada
```

Hoặc sử dụng cURL:

```bash
curl -i http://localhost:8080/greetings/Ada
curl -i http://localhost:8080/api/greetings/Ada
curl -i -X POST http://localhost:8080/signup \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "name=Ada&email=ada@example.com"
```

Kết quả kỳ vọng:

- `GET /greetings/Ada` trả 200 với HTML có `<h1>Xin chào, Ada!</h1>`, được render từ template.
- `GET /api/greetings/Ada` trả 200 với JSON body `{"message":"Xin chào, Ada!"}`; không cần template.
- `POST /signup` hợp lệ trả redirect (thường HTTP 302) tới `/signup/done`; request GET sau đó có thể dùng flash attribute hiển thị `Đã đăng ký: Ada`.
- `POST /signup` với `name=` trống sẽ render lại template signup; controller tự chọn trả view và mặc định có thể HTTP 200 dù validation lỗi được hiển thị trong trang. Đây không phải tình huống REST API tự động trả 400.

Dùng `curl.exe` trên Windows PowerShell nếu `curl` là alias khác; cú pháp nối dòng bằng `\` ở trên dành cho shell POSIX.

## 8. Kiểm thử MVC view resolution bằng MockMvc

File `src/test/java/example/ViewResolutionTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class ViewResolutionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void homeRendersTemplateAndModel() throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(view().name("home"))
            .andExpect(content().string(
                    containsString("<h1>Trang chủ MVC</h1>")));
    }

    @Test
    void nestedLogicalViewResolvesCorrectTemplate() throws Exception {
        mvc.perform(get("/greetings/Ada"))
            .andExpect(status().isOk())
            .andExpect(view().name("greetings/detail"))
            .andExpect(content().string(
                    containsString("<h1>Xin chào, Ada!</h1>")));
    }

    @Test
    void modelAndViewAlsoWorks() throws Exception {
        mvc.perform(get("/model-view"))
            .andExpect(status().isOk())
            .andExpect(view().name("home"))
            .andExpect(content().string(
                    containsString("Trang ModelAndView")));
    }

    @Test
    void restControllerWritesJsonWithoutView() throws Exception {
        mvc.perform(get("/api/greetings/Ada"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.message")
                    .value("Xin chào, Ada!"));
    }

    @Test
    void invalidFormReturnsSameTemplateWithBindingErrors()
            throws Exception {
        mvc.perform(post("/signup")
                    .param("name", "")
                    .param("email", "ada@example.com"))
            .andExpect(status().isOk())
            .andExpect(view().name("signup"))
            .andExpect(model().attributeHasFieldErrors(
                    "signupForm", "name"));
    }

    @Test
    void validFormRedirectsWithFlashAttribute() throws Exception {
        mvc.perform(post("/signup")
                    .param("name", "Ada")
                    .param("email", "ada@example.com"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signup/done"))
            .andExpect(flash().attribute(
                    "notice", "Đã đăng ký: Ada"));
    }
}
```

Chạy `mvn test`. Hai phép kiểm tra khác nhau cần chú ý: `view().name(...)` xác nhận tên logic controller trả về, còn `content().string(...)` xác nhận HTML đã render với dữ liệu từ model. Nếu chỉ assert view name mà không thử nội dung hoặc resource, test có thể “xanh” ngay cả khi template thực tế không tồn tại hoặc engine không chạy.

`MockMvc` chạy trong test context, không yêu cầu mở cổng HTTP. Với `@WebMvcTest` dạng slice, cần bảo đảm view engine configuration/resources cần thiết được nạp; ví dụ sử dụng `@SpringBootTest` + `@AutoConfigureMockMvc` để đi qua đúng auto-configuration đầy đủ.

## 9. Tích hợp nhiều engine: đường đi và chiến lược migration

Nếu cùng duy trì Thymeleaf và JSP hoặc Thymeleaf và FreeMarker:

1. Xác định nhóm view name theo công nghệ, ví dụ `pages/*` cho Thymeleaf, `legacy/*` cho JSP.
2. Đặt giới hạn tên view trên engine phù hợp; Thymeleaf hỗ trợ `spring.thymeleaf.view-names` và `spring.thymeleaf.excluded-view-names`.
3. Kiểm tra ViewResolver `order` thực tế từ ApplicationContext. Resolver có độ chính xác cao hoặc chỉ nhận tên cụ thể nên đứng sớm; JSP InternalResource resolver đứng cuối.
4. Bảo đảm tên không thuộc nhóm một engine **không bị engine đó giữ lại** và báo lỗi template trong bước render.
5. Viết test cho một HTML Thymeleaf page, một JSP page (nếu có), một custom View và một JSON endpoint.
6. Kiểm tra packaging: JSP cần Servlet container/packaging hỗ trợ; nhiều mẫu Boot JAR nên ưu tiên template engines hỗ trợ classpath.
7. Giữ model contract rõ ràng khi di chuyển từ engine cũ sang mới, để frontend còn hiển thị dữ liệu và lỗi form đúng.

**Không thể chỉ đổi suffix từ `.jsp` sang `.html` rồi coi là migration hoàn chỉnh:** cú pháp template, tag library, security escaping, layout, form binding và cách cache có thể khác.

## 10. Chẩn đoán lỗi view resolution

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Browser thấy chữ `home` thay vì HTML | Method `@ResponseBody` hoặc class `@RestController` | Dùng `@Controller`/view name thay cho response body |
| Không tìm thấy `home.html` | Prefix/suffix sai hoặc file không nằm trên classpath | Kiểm tra `templates/home.html` và `spring.thymeleaf.*` |
| Thymeleaf không được gọi, request chuyển JSP | JSP resolver đứng trước hoặc view names không khoanh vùng | Kiểm tra order và giới hạn resolver |
| View name đúng, response lỗi 500 | Template lỗi cú pháp, thiếu resource, lỗi biểu thức hoặc render | Xem cause/log Thymeleaf, template path |
| GET request trả 404 | Không có HTTP handler, hoặc logic/resource khác | Kiểm tra HandlerMapping trước ViewResolver |
| Redirect bất ngờ thêm query parameters | Model attributes được đưa vào redirect ngoài dự kiến | Dùng `RedirectAttributes` tường minh |
| Submit form lỗi nhưng mất thông báo | Redirect sang request mới khi chưa chuyển flash state | Trả về form view trong cùng request |
| `th:text` rỗng | Model thiếu attribute hoặc sai tên | Kiểm tra `model.addAttribute(...)` và biểu thức |
| Sửa template nhưng không thấy đổi | Template engine cache hoặc HTTP cache | Xác định cache layer và chỉ tắt cache dev |
| Có JSON trên API nhưng không có HTML | `@RestController`/message converter đang hoạt động đúng | Tách controller API và trang HTML theo ý định |
| Accept PDF nhưng không ra PDF | Không có View hỗ trợ media type PDF | Đăng ký View thực tế, đừng mong content negotiation tự tạo file |
| Đổi `spring.mvc.view.prefix` không ảnh hưởng Thymeleaf | Đang thay cấu hình JSP/Servlet resolver | Dùng `spring.thymeleaf.prefix/suffix` |
| Bật `@EnableWebMvc` làm thay đổi nhiều hành vi | Ghi đè phần lớn MVC auto-configuration | Tùy chỉnh qua Boot properties/`WebMvcConfigurer` trước |

### 10.1. Các bước debug nên làm

1. Kiểm tra **controller nào được chọn**, return type, annotation trên method/class và logical view name thực tế.
2. Nếu đang xử lý `@ResponseBody`/`ResponseEntity`, kiểm tra **HTTP message converter**, không chỉnh resolver template.
3. Liệt kê ViewResolver beans, mức `order`, danh sách view names và bean nào có thể trả null.
4. Kiểm tra template nằm tại đường dẫn dự kiến theo prefix/suffix; giữ nhất quán chữ hoa/thường.
5. Đọc stack trace để phân biệt **handler không tồn tại**, **resolver không chọn được View**, **View render lỗi**.
6. Dùng `MockMvc` assert cả `view().name(...)` lẫn body HTML; với JSON assert media type và body riêng.
7. Khi cache gây khó hiểu, kiểm tra lần lượt resolver cache, template engine cache và HTTP/browser cache.

Có thể bật debug log trong môi trường phát triển:

```properties
logging.level.org.springframework.web.servlet.view=DEBUG
logging.level.org.thymeleaf=INFO
```

Khi test cần thêm thông tin, dùng `andDo(print())` trên `MockMvc` để quan sát model, view name và response. Không log/đưa ra response dữ liệu nhạy cảm từ model trong production.

## 11. An toàn khi render template

- Dùng `th:text` cho input không tin cậy vì nó HTML-escape nội dung; thận trọng với `th:utext` vì nó có thể render HTML chưa được làm sạch.
- Không cho client tùy chọn trực tiếp tên template/view tùy ý rồi return; chỉ sử dụng tên trong whitelist rõ ràng.
- Đừng ghép `redirect:` với URL do client cung cấp nếu chưa kiểm tra host/path, để tránh open redirect.
- Giữ bí mật và field nội bộ khỏi model, HTML hidden input, JavaScript và server-rendered markup.
- Với biểu mẫu, validation không thay thế CSRF và authorization; áp dụng cơ chế bảo vệ tương ứng.
- Trong production, chọn cache template hợp lý và gắn phiên bản asset; không vô hiệu hóa cache toàn hệ thống chỉ để thuận tiện debug.
- `forward:` không phải cách vượt authorization. Cấu hình security filter có thể áp dụng khác nhau theo dispatcher type, cần kiểm chứng với hệ thống thật.

## 12. Câu hỏi tự kiểm tra

1. Controller `@Controller` return `"books/detail"` nghĩa là gì? **Tên view logic**, chưa phải HTML body hay URL browser.
2. Ai quyết định controller nào xử lý `GET /books/7`? **HandlerMapping**, không phải ViewResolver.
3. `ViewResolver` và `View` khác nhau ra sao? **Resolver chọn View; View render model vào response**.
4. Hai resolver có order `0` và `100` thì ai chạy trước? **Order 0**.
5. Vì sao JSP `InternalResourceViewResolver` đứng cuối? **Không thể xác minh JSP tồn tại trước khi Servlet dispatch và dễ chiếm mọi tên**.
6. `BeanNameViewResolver` có render service bean cùng tên không? **Không**, cần bean kiểu `View`.
7. Thymeleaf mặc định trong Boot tìm `"home"` ở đâu? **`classpath:/templates/home.html`**, nếu giữ prefix/suffix mặc định.
8. Khi method gắn `@ResponseBody` return `"home"`, Thymeleaf render không? **Không**, chữ home được viết trực tiếp vào body.
9. `ContentNegotiatingViewResolver` có tự biến object Java thành JSON? **Không**; nó chọn View khác theo media type. JSON REST thường dùng message converter.
10. `redirect:/orders/7` có tương đương template `orders/7.html` không? **Không**, redirect tới URL mới.
11. Form invalid nên trả lại template hay redirect ngay? **Thường trả lại template cùng request** để giữ BindingResult.
12. Đặt `spring.thymeleaf.template-resolver-order` có đổi thứ tự giữa Thymeleaf và JSP ViewResolver không? **Không**; đó là một mức thứ tự nội bộ của template engine.
13. Nếu view name đúng mà HTML lỗi, luôn là 404? **Không**, template render exception có thể gây HTTP 500.
14. Khi test chỉ thấy `view().name("home")` đúng thì template có chắc render được không? **Chưa chắc**; thêm assert HTML thật.
15. Vì sao tránh `th:utext` cho tên người dùng? **Vì có thể đưa markup không tin cậy vào HTML và gây XSS**.

## 13. Tài liệu chính thức

- [Spring Framework 6.2 — View Resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/viewresolver.html): contract của `ViewResolver`/`View`, chaining, JSP-last, redirect/forward và content negotiation.
- [Spring Framework 6.2 — MVC View Resolvers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/view-resolvers.html): API cấu hình resolver qua `WebMvcConfigurer`.
- [Spring Framework 6.2 — JSP and JSTL](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-view/mvc-jsp.html): JSP resolver và `JstlView`.
- [Spring Boot 3 — Spring MVC How-to](https://docs.spring.io/spring-boot/3.3/how-to/spring-mvc.html): resolver beans mặc định và tích hợp template engines.
- [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html): `spring.thymeleaf.prefix`, suffix, cache, view-names và các properties khác.
- [Thymeleaf + Spring Tutorial](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): Spring MVC/Thymeleaf, expressions, forms và validation.

**Ghi nhớ:** `@Controller` trả tên view logic; MVC lần lượt hỏi các `ViewResolver` theo mức ưu tiên, tìm `View` phù hợp, rồi View render model bằng template engine hoặc Servlet/JSP. `@RestController` và `@ResponseBody` đi qua message converter. Chọn đúng pipeline trước khi điều chỉnh resolver và prefix/suffix.

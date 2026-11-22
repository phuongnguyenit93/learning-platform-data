# ViewResolver và dựng giao diện từ tên view trong Spring MVC

## 1. Mục tiêu bài học

Trong một ứng dụng Spring MVC hiển thị HTML phía server, controller thường **không tự xây dựng toàn bộ chuỗi HTML**. Thay vào đó, controller thực hiện nghiệp vụ, đưa dữ liệu vào `Model` và trả về một **tên view logic** như `"welcome"`, `"products/list"` hoặc `"orders/detail"`.

Spring MVC sử dụng `ViewResolver` để chuyển tên logic đó thành một đối tượng `View` có thể dựng trang. `View` kết hợp dữ liệu trong model với template tương ứng, tạo HTTP response gửi cho trình duyệt.

Ví dụ:

```java
@GetMapping("/welcome")
public String welcome(Model model) {
    model.addAttribute("name", "Lan");
    return "welcome";
}
```

Ở đây `"welcome"` là **tên view**, không phải nội dung response, cũng không phải URL `/welcome`. Với Thymeleaf được Spring Boot cấu hình mặc định, tên này thường ánh xạ tới `src/main/resources/templates/welcome.html`.

Bài học tập trung vào cơ chế phía **Spring MVC/Servlet stack**: luồng thực thi, các loại resolver, cấu hình Spring Boot, ví dụ chạy thực tế, xử lý chuyển hướng và lỗi thường gặp. Spring WebFlux cũng có khái niệm `ViewResolver` nhưng là API khác.

## 2. Vai trò của DispatcherServlet, ModelAndView, ViewResolver và View

| Thành phần | Vai trò chính | Khi nào tham gia? |
|---|---|---|
| `DispatcherServlet` | Front Controller điều phối HTTP request, handler, kết quả xử lý và dựng response | Xuyên suốt luồng MVC |
| `HandlerMapping` | Tìm handler/controller phù hợp với URL và HTTP method | Trước khi gọi controller |
| `HandlerAdapter` | Gọi method của controller, xử lý tham số/giá trị trả về | Trong giai đoạn xử lý request |
| `Model` | Tập hợp các thuộc tính mà view sử dụng khi render | Controller hoặc model binder bổ sung dữ liệu |
| `ModelAndView` | Đại diện cho model cùng tên `View` hoặc một `View` cụ thể | Khi controller/handler đã xử lý |
| `ViewResolver` | Phân giải tên view logic thành đối tượng `View` | Khi kết quả cần được dựng thành view |
| `View` | Render model thành response theo công nghệ giao diện cụ thể | Sau khi view được phân giải |

Interface cốt lõi của Spring MVC:

```java
package org.springframework.web.servlet;

public interface ViewResolver {
    View resolveViewName(String viewName, java.util.Locale locale)
            throws Exception;
}
```

Đây là chữ ký **minh họa rút gọn** của phương thức trong API, không phải file Java để tạo lại interface có sẵn. `resolveViewName` có thể trả về `null` để báo resolver hiện tại không giải quyết được tên view.

Còn `View` có nhiệm vụ dựng response từ dữ liệu model. Khi controller trả về một đối tượng `View` trực tiếp, Spring MVC có thể sử dụng đối tượng đó mà không cần giải tên view qua chuỗi resolver.

## 3. Toàn bộ luồng dựng giao diện

Sơ đồ cho một HTTP request phục vụ HTML:

```text
GET /welcome?name=Lan
        |
        v
DispatcherServlet
        |
        v
HandlerMapping -> HandlerAdapter
        |
        v
@Controller#method(...)
  model.addAttribute("name", "Lan")
  return "welcome"
        |
        v
ModelAndView (viewName = "welcome", model = { name: "Lan" })
        |
        v
DispatcherServlet xử lý view
        |
        v
ViewResolver.resolveViewName("welcome", locale)
        |
        v
View (ví dụ ThymeleafView)
        |
        v
View.render(model, request, response)
        |
        v
Template + model -> HTML response
        |
        v
Trình duyệt hiển thị giao diện
```

Diễn giải từng bước:

1. Browser gửi request tới ứng dụng; `DispatcherServlet` tiếp nhận theo cấu hình servlet mapping.
2. `HandlerMapping` tìm method `@GetMapping("/welcome")`; `HandlerAdapter` gọi method và xử lý các tham số như `Model`, `@RequestParam`.
3. Controller thêm `name = "Lan"` vào model và trả `"welcome"`.
4. Spring MVC hiểu giá trị kiểu `String` trong `@Controller` thông thường là **tên view**, tập hợp tên view và model để render. Controller cũng có thể trả `ModelAndView` trực tiếp.
5. `DispatcherServlet` duyệt các `ViewResolver` thích hợp để tìm một `View` cho tên `welcome`.
6. Một template resolver như Thymeleaf tìm/đánh giá template tương ứng, sử dụng model và locale theo quy tắc của công nghệ đó.
7. `View.render(...)` ghi nội dung response, thường là HTML với `Content-Type: text/html`.

Vì vậy, **`ViewResolver` làm nhiệm vụ tìm hoặc tạo đối tượng View; View mới là thành phần render**. Không nên nhầm resolver với controller, template engine, HTTP client hoặc một thư mục cụ thể.

## 4. Tên view logic khác file template và URL như thế nào?

Giả sử controller trả:

```java
return "pages/welcome";
```

Với Thymeleaf mặc định của Spring Boot:

```text
View name:       pages/welcome
Template prefix: classpath:/templates/
Template suffix: .html
Template:        classpath:/templates/pages/welcome.html
Source file:     src/main/resources/templates/pages/welcome.html
```

Không phải lúc nào resolver cũng chỉ nối prefix/suffix. Chẳng hạn `BeanNameViewResolver` ánh xạ tên với một bean `View`, còn `ContentNegotiatingViewResolver` có thể phối hợp nhiều resolver để chọn representation dựa trên media type.

Ba địa chỉ dưới đây có ý nghĩa khác nhau:

- URL `/welcome`: định tuyến HTTP, được `HandlerMapping` dùng để tìm controller.
- Tên view `pages/welcome`: tên logic controller trả về để Spring MVC phân giải.
- Resource template `classpath:/templates/pages/welcome.html`: file hoặc tài nguyên mà template engine dùng để dựng HTML.

Đổi `@GetMapping("/welcome")` thành `@GetMapping("/hello")` không bắt buộc phải đổi tên view. Nhiều URL cũng có thể cùng trả một view, chỉ khác model.

## 5. Ví dụ Spring Boot 3.x + Java 17 + Thymeleaf

Ví dụ này là một ứng dụng Spring Boot 3.x dùng **Spring MVC (Servlet)** và **Thymeleaf**. Cần có project Maven Java 17 với các dependency:

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
</dependencies>
```

Đây là phần `<dependencies>` cho `pom.xml` **đã có Spring Boot parent hoặc dependency management**, không phải toàn bộ POM độc lập. Tạo project bằng Spring Initializr với Java 17 và chọn `Spring Web`, `Thymeleaf`; cấu trúc file cần có:

```text
src/main/
  java/com/example/mvcdemo/
    MvcDemoApplication.java
    WelcomeController.java
  resources/
    application.properties
    templates/
      pages/
        welcome.html
```

### 5.1. Class main

File `src/main/java/com/example/mvcdemo/MvcDemoApplication.java`:

```java
package com.example.mvcdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcDemoApplication.class, args);
    }
}
```

### 5.2. Controller trả tên view và dữ liệu model

File `src/main/java/com/example/mvcdemo/WelcomeController.java`:

```java
package com.example.mvcdemo;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class WelcomeController {

    @GetMapping("/welcome")
    public String welcome(
            @RequestParam(defaultValue = "Khách") String name,
            Model model) {
        model.addAttribute("name", name);
        return "pages/welcome";
    }
}
```

Phân tích:

- `@Controller` tham gia cơ chế Spring MVC dựng view.
- `@GetMapping("/welcome")` gắn đường dẫn HTTP với handler method.
- `@RequestParam(defaultValue = "Khách")` nhận giá trị tham số `name`; khi bỏ qua, dùng giá trị mặc định.
- `model.addAttribute("name", name)` cho template truy cập giá trị bằng biểu thức `${name}`.
- `return "pages/welcome"` là tên view logic; Spring MVC chuyển tên này cho chuỗi resolver.

### 5.3. Template Thymeleaf

File `src/main/resources/templates/pages/welcome.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Trang chào mừng</title>
</head>
<body>
    <h1>Xin chào, <span th:text="${name}">Khách</span>!</h1>
    <a th:href="@{/welcome(name='Minh')}">Chào Minh</a>
</body>
</html>
```

Thymeleaf xử lý `th:text="${name}"` bằng dữ liệu từ model. Nội dung văn bản được HTML-escape theo mặc định, giúp tránh chèn HTML tùy ý từ tham số người dùng. `th:href` tạo URL theo ngữ cảnh ứng dụng.

Chú ý file `welcome.html` nằm trong **`templates/pages`**, không phải `static/pages`. Thư mục `static` phù hợp cho CSS, JavaScript, ảnh và những tài nguyên tĩnh được phục vụ trực tiếp.

### 5.4. Cấu hình (không bắt buộc với giá trị mặc định)

File `src/main/resources/application.properties`:

```properties
server.port=8080
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.mode=HTML

# Chỉ nên tắt cache template trong lúc phát triển
spring.thymeleaf.cache=false
```

Các thuộc tính `prefix` và `suffix` thường đã có giá trị mặc định đúng như ví dụ. Việc ghi ra giúp dễ hiểu đường đi từ `"pages/welcome"` tới `templates/pages/welcome.html`.

Trong production, thường để template cache được bật để giảm chi phí phân giải và xử lý template. Không để cấu hình phát triển ảnh hưởng hiệu năng sản phẩm mà không có lý do.

### 5.5. Chạy thử

Tại thư mục gốc project Maven có `mvnw`:

```bash
./mvnw spring-boot:run
```

Trong terminal khác:

```bash
curl -s "http://localhost:8080/welcome?name=Lan"
```

Trong HTML response sẽ có đoạn tương đương:

```html
<h1>Xin chào, <span>Lan</span>!</h1>
```

Đây là **một đoạn HTML được render**, không phải toàn bộ response theo byte: tài liệu HTML còn có các thẻ `html`, `head`, `body` và liên kết. Nếu truy cập `/welcome` không có tham số, trang dùng tên mặc định `Khách`.

Sau khi chạy, đổi view name thành `"pages/other"` mà không tạo `templates/pages/other.html` sẽ khiến Thymeleaf không tìm được template; kết quả thường là lỗi khi phân giải hoặc render view. Đó là cách xác nhận rằng tên view chỉ được sử dụng làm khóa phân giải template.

## 6. Khác biệt giữa @Controller, @RestController và @ResponseBody

Hai method sau có cùng kiểu trả về `String` nhưng **ngữ nghĩa khác nhau**:

```java
@Controller
class HtmlController {
    @GetMapping("/page")
    String page() {
        return "pages/welcome";
    }
}
```

Trong `@Controller` thông thường, Spring MVC hiểu `"pages/welcome"` là tên view.

```java
@RestController
class ApiController {
    @GetMapping("/api/message")
    String message() {
        return "pages/welcome";
    }
}
```

Trong `@RestController`, `String` được ghi vào **HTTP response body** như văn bản; Spring MVC không gọi `ViewResolver` để tìm `pages/welcome.html`. `@RestController` tương đương việc áp dụng `@Controller` cùng `@ResponseBody` ở cấp lớp.

Tương tự:

```java
@Controller
class PlainTextController {
    @GetMapping("/plain")
    @ResponseBody
    String plain() {
        return "Không dùng ViewResolver";
    }
}
```

Method có `@ResponseBody` đi theo cơ chế `HttpMessageConverter` để tạo body. API trả JSON bằng `ResponseEntity<...>` hoặc `@ResponseBody` thường không dùng `ViewResolver`.

Đây là một trong những nguyên nhân dễ gặp nhất khi người mới làm Spring MVC thấy trang web chỉ hiển thị chữ `welcome`: controller đã bị đánh dấu `@RestController`.

## 7. Dùng ModelAndView khi muốn gói view và model cùng nhau

Thay vì thêm vào `Model` rồi trả `String`, controller có thể trả `ModelAndView`:

```java
package com.example.mvcdemo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.servlet.ModelAndView;

@Controller
public class ProfileController {

    @GetMapping("/profile")
    public ModelAndView profile() {
        ModelAndView mv = new ModelAndView("pages/profile");
        mv.addObject("displayName", "Mai");
        mv.addObject("role", "Member");
        return mv;
    }
}
```

Spring MVC nhận `ModelAndView` chứa tên `pages/profile` và hai thuộc tính model. Để endpoint hoạt động cần thêm `src/main/resources/templates/pages/profile.html`, trong đó có thể truy cập `${displayName}` và `${role}`.

`ModelAndView` cũng có thể được khởi tạo từ một đối tượng `View` thay vì tên logic. Khi `ModelAndView` đã chứa `View` cụ thể, bước giải tên view không cần thiết.

Đối với controller nhỏ, `Model` + `String` thường dễ đọc. `ModelAndView` hữu ích khi cần gói rõ view và model vào một giá trị trả về.

## 8. Các ViewResolver thường gặp

| Resolver | Cách giải tên view | Ví dụ sử dụng |
|---|---|---|
| `ThymeleafViewResolver` | Dùng cấu hình Thymeleaf để chọn template HTML và tạo `View` | `"pages/welcome"` → `templates/pages/welcome.html` |
| `InternalResourceViewResolver` | Gắn prefix/suffix để tạo internal resource; hỗ trợ JSP, Servlet dispatch | `"orders/list"` → `/WEB-INF/jsp/orders/list.jsp` |
| `BeanNameViewResolver` | Tìm bean `View` trong ApplicationContext có tên khớp view name | Một bean `View` tên `reportView` |
| `FreeMarkerViewResolver` | Ánh xạ tên view với template FreeMarker | Trang `.ftlh` |
| `ContentNegotiatingViewResolver` | Phối hợp các resolver/view khác để chọn representation phù hợp `Accept` và media type | HTML, XML, PDF khi đã cấu hình các view tương ứng |

Spring Boot có thể auto-configure một số resolver dựa vào dependency và môi trường web. Nếu thêm Thymeleaf starter vào ứng dụng MVC, Spring Boot thường tự đăng ký `ThymeleafViewResolver` và template engine. Do đó, ví dụ mục 5 không cần tự tạo bean resolver.

### 8.1. InternalResourceViewResolver và JSP

Với JSP, ý tưởng ánh xạ:

```properties
spring.mvc.view.prefix=/WEB-INF/jsp/
spring.mvc.view.suffix=.jsp
```

Nếu controller trả `"orders/list"`, resource dự kiến là `/WEB-INF/jsp/orders/list.jsp`. Điều này **chỉ phù hợp khi ứng dụng được triển khai với JSP engine và cấu trúc resource đúng**; thêm prefix/suffix không tự mang JSP compiler vào project.

JSP có một số giới hạn với embedded servlet container và đóng gói executable JAR; Spring Boot khuyến nghị cân nhắc template engine như Thymeleaf hoặc FreeMarker nếu có thể. Với ứng dụng JSP truyền thống, cần kiểm tra dependency Jasper, loại packaging và cấu trúc `src/main/webapp/WEB-INF/jsp/` theo server đang dùng.

Hai property `spring.mvc.view.prefix` và `spring.mvc.view.suffix` dành cho resolver dạng internal resource; chúng **không phải** cách sửa đường dẫn template của Thymeleaf. Thymeleaf dùng `spring.thymeleaf.prefix`, `spring.thymeleaf.suffix`.

### 8.2. BeanNameViewResolver

`BeanNameViewResolver` dùng chính tên bean làm tên view logic. Ví dụ một bean có tên `reportView` và kiểu `View` có thể được chọn khi controller trả `"reportView"`. Cách này hữu ích nếu `View` là một thành phần tự viết hoặc tạo dữ liệu ở định dạng đặc biệt.

Một `@Component("reportView")` không đủ nếu component đó không triển khai `View`; resolver tìm **View bean**, không phải bean bất kỳ.

### 8.3. ContentNegotiatingViewResolver

Resolver này có nhiệm vụ điều phối, chứ không trực tiếp tạo template. Nó so sánh loại nội dung client chấp nhận (thường từ `Accept` header) với những `View` phù hợp do các resolver khác cung cấp. Nếu nhiều công nghệ giao diện cùng tham gia, cần cấu hình đúng media type, resolver order và default views.

Không nhầm `ContentNegotiatingViewResolver` với JSON serialization mặc định của `@ResponseBody`: hai luồng xử lý khác nhau.

## 9. Chuỗi nhiều resolver và thứ tự ưu tiên

Spring MVC có thể đăng ký **nhiều** `ViewResolver`. Chúng được sắp xếp theo `Ordered`, `@Order` hoặc cấu hình order tương ứng. Resolver với **số order nhỏ hơn** thường được thử sớm hơn.

Khái quát:

```text
View name = "report"
        |
        v
Resolver thứ nhất
  -> View? có: dùng View
  -> null? chuyển sang resolver tiếp
        |
        v
Resolver thứ hai
  -> View? có: dùng View
  -> null? chuyển tiếp
        |
        v
Không có view phù hợp -> lỗi phân giải/render
```

Quan trọng:

- Resolver có thể trả `null` khi không phân giải được; `DispatcherServlet` tiếp tục tìm resolver khác.
- Một resolver có thể **tạo đối tượng View từ quy tắc prefix/suffix dù tài nguyên thật chưa tồn tại**; lỗi có thể chỉ xảy ra khi render. Vì vậy, không nên cho rằng mỗi resolver đều kiểm tra file tồn tại trước khi trả về view.
- `InternalResourceViewResolver` với JSP thường phải đứng **cuối chuỗi**: trước lúc dispatch bằng `RequestDispatcher`, nó khó xác định chắc chắn JSP có tồn tại hay không, nên có thể giành view của resolver khác.
- Tránh đăng ký nhiều resolver cùng có thể nhận cùng một tên view mà không xác định thứ tự rõ ràng. Khi hỗ trợ cả Thymeleaf và JSP, cần kiểm soát tên view, prefix/suffix, order và cơ chế kiểm tra resource.

Khi Spring Boot auto-configure các resolver, không tự tạo bean cùng tên/kiểu mà chưa hiểu hậu quả tới auto-configuration. Với nhu cầu đơn giản, dùng starter và cấu hình property là đủ.

## 10. redirect: và forward: là tên view đặc biệt

### 10.1. Redirect thay đổi URL phía client

`redirect:` là một prefix đặc biệt được các resolver hỗ trợ nhận biết để tạo HTTP redirect:

```java
@Controller
class NavigationController {

    @GetMapping("/old-page")
    public String oldPage() {
        return "redirect:/welcome";
    }
}
```

Khi browser yêu cầu `/old-page`, server trả HTTP response chuyển hướng (thường thuộc nhóm 3xx, ví dụ 302) với `Location` phù hợp. Browser gửi **request mới** tới `/welcome`; URL trên thanh địa chỉ thay đổi. Đây không phải hành động render template `templates/redirect:/welcome.html`.

Dùng redirect sau POST để tránh gửi lại biểu mẫu khi người dùng reload trang (mẫu **Post/Redirect/Get**). Ví dụ:

```java
@PostMapping("/contacts")
public String saveContact(
        @RequestParam String name,
        RedirectAttributes redirectAttributes) {
    // Phần lưu thông tin vào service được triển khai trong ứng dụng.
    redirectAttributes.addFlashAttribute("notice", "Đã lưu " + name);
    return "redirect:/contacts";
}
```

Đoạn này là **minh họa trong một `@Controller`** và cần import `PostMapping`, `RequestParam`, `RedirectAttributes` đúng package Spring. `addFlashAttribute` truyền dữ liệu qua redirect bằng flash attributes để request kế tiếp có thể sử dụng; không nên nhét thông tin nhạy cảm vào query string.

Không tạo redirect tới URL tùy ý nhận trực tiếp từ client mà thiếu kiểm soát, vì có nguy cơ **open redirect**.

### 10.2. Forward giữ request phía server

Prefix `forward:` yêu cầu xử lý tiếp ở phía server thông qua `RequestDispatcher.forward()`, ví dụ:

```java
@GetMapping("/legacy")
public String legacy() {
    return "forward:/welcome";
}
```

Ở đây Spring MVC forward nội bộ tới đường dẫn `/welcome`. Browser không tự thực hiện một request mới theo cơ chế redirect và URL đang hiển thị không nhất thiết thay đổi.

| Khía cạnh | `redirect:/welcome` | `forward:/welcome` |
|---|---|---|
| Bản chất | Response chuyển hướng | Server-side dispatch |
| HTTP request | Client thường thực hiện request mới | Tiếp tục trong cùng vòng request/dispatch |
| URL trên browser | Thường đổi sang URL đích | Thường giữ URL ban đầu |
| Dữ liệu chuyển theo | Query params, flash attributes hoặc cơ chế khác | Request attributes và trạng thái request trong phạm vi forward |
| Mục đích | Điều hướng, Post/Redirect/Get | Chuyển nội bộ đến handler/tài nguyên |

Đừng nhầm `forward:` với việc resolve tên template thông thường. Không phải tất cả view technology đều cần hoặc nên dùng `forward:`.

## 11. View Controllers: dựng template mà không cần controller có logic

Nếu một trang tĩnh theo mẫu chỉ cần ánh xạ URL đến template, có thể cấu hình trực tiếp qua `WebMvcConfigurer`:

```java
package com.example.mvcdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ViewRouteConfig implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addViewController("/help")
                .setViewName("pages/help");
    }
}
```

Khi truy cập `/help`, Spring MVC chọn tên `pages/help` rồi resolve tới template phù hợp, ví dụ `templates/pages/help.html`.

Nếu dùng `WebMvcConfigurer` để mở rộng cấu hình MVC của Spring Boot, thường **không cần thêm `@EnableWebMvc`**. Đánh dấu `@EnableWebMvc` có thể làm thay đổi cơ chế auto-configuration mà Boot cung cấp, tạo thêm công việc cấu hình thủ công.

## 12. Dữ liệu model, escaping, layout và static resources

Trong server-side rendering, model có thể được tạo từ:

- `Model.addAttribute(...)` hoặc `ModelMap`.
- Giá trị trả về hoặc tham số `@ModelAttribute`.
- `ModelAndView.addObject(...)`.
- Một số flash attributes sau redirect.

Template truy cập model để dựng danh sách, thông báo, form hoặc bảng. Ví dụ Thymeleaf:

```html
<p th:text="${message}">Nội dung mặc định</p>
<ul>
    <li th:each="product : ${products}"
        th:text="${product.name}">Sản phẩm</li>
</ul>
```

Code trên là fragment mẫu; controller phải đưa `message` và `products` vào model. Thymeleaf có thể render layout hoặc fragment dùng chung (header, footer, navigation); đây là chức năng template engine, **không phải thuật toán định tuyến HTTP của `ViewResolver`**.

An toàn khi dựng giao diện:

- `th:text` HTML-escape dữ liệu theo ngữ cảnh; ưu tiên dùng cho dữ liệu do user nhập.
- `th:utext` render nội dung HTML không escape; cần làm sạch/kiểm soát dữ liệu nếu buộc phải dùng.
- Không đưa dữ liệu nhạy cảm, session token hoặc secret vào model được render ra HTML.
- Khi dùng form, kiểm tra CSRF và validation theo Spring Security/Bean Validation nếu ứng dụng có các thành phần đó.
- Tài nguyên CSS/JS/ảnh được phục vụ riêng, ví dụ `src/main/resources/static/css/site.css`; view resolution không phải là cách chung để phục vụ file tĩnh.

## 13. Kiểm thử controller và tên view

Ngoài chạy thủ công, `MockMvc` có thể kiểm tra tên view và thuộc tính model. Ví dụ kiểm thử Spring Boot 3.x, giả định project có `spring-boot-starter-test`:

File `src/test/java/com/example/mvcdemo/WelcomeControllerTest.java`:

```java
package com.example.mvcdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class WelcomeControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void rendersNamedViewWithModel() throws Exception {
        mockMvc.perform(get("/welcome").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(view().name("pages/welcome"))
                .andExpect(model().attribute("name", "Lan"));
    }
}
```

Lệnh chạy trên project Maven có Maven Wrapper:

```bash
./mvnw test
```

Kiểm thử xác nhận controller chọn đúng view name và model; test rendering HTML thực tế cần template hiện diện và cấu hình tương ứng. Để chắc chắn nội dung HTML đến browser phù hợp, có thể bổ sung kiểm thử `MockMvc` trên response HTML hoặc integration test HTTP.

Kiểm tra bằng browser cũng rất hữu ích: mở Developer Tools, tab Network, xác nhận status, `Content-Type`, response body và redirect chain. Nếu template không tìm được, đọc stacktrace/exception nguyên gốc thay vì chỉ quan sát một trang lỗi chung.

## 14. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Browser chỉ hiển thị chữ `pages/welcome` | Controller dùng `@RestController` hoặc `@ResponseBody` | Dùng `@Controller` và trả tên view để dựng HTML |
| Không tìm thấy template | Sai view name, sai đường dẫn `templates/`, sai prefix/suffix hoặc thiếu dependency template engine | Kiểm tra resource thật trong classpath, đường dẫn và cấu hình Thymeleaf |
| View render nhưng model không có dữ liệu | Quên `addAttribute` hoặc dùng tên key khác template | So khớp `model.addAttribute("name", ...)` với `${name}` |
| Thêm JSP nhưng không chạy | Thiếu JSP engine, packaging không phù hợp hoặc sai `/WEB-INF/` | Xem giới hạn JSP với embedded container và cấu hình Maven/Gradle |
| Thymeleaf không nhận `spring.mvc.view.prefix` | Đó là property của internal resource resolver | Dùng `spring.thymeleaf.prefix` và `spring.thymeleaf.suffix` |
| Nhiều resolver chọn nhầm view | Thứ tự `ViewResolver` hoặc resolver nhận quá nhiều tên | Xem order, ưu tiên resolver cụ thể và để `InternalResourceViewResolver` cuối |
| Dùng `return "redirect:/..."` nhưng không chuyển hướng | Có `@ResponseBody` hoặc xử lý kiểu trả về khác | Xác nhận MVC view-name flow và response 3xx |
| Browser báo lỗi sau khi submit POST | Redirect path sai hoặc endpoint đích thiếu handler | Kiểm tra `Location` và mapping đích |
| Lỗi circular view path | View name mặc định hoặc forward quay về chính handler | Trả tên view rõ ràng và kiểm tra prefix/suffix, target path |
| Template cũ vẫn hiển thị sau sửa | Template cache hoặc ứng dụng chưa reload resource | Tắt cache khi phát triển, rebuild/redeploy khi cần |
| Mọi trang MVC thay đổi sau thêm `@EnableWebMvc` | Thay đổi cơ chế auto-configured MVC | Bỏ `@EnableWebMvc` nếu chỉ muốn thêm `WebMvcConfigurer` |

### Debug theo thứ tự

1. Xác định URL request và method/controller thực sự được chọn.
2. Kiểm tra có `@Controller` hay `@RestController`, `@ResponseBody` không.
3. Ghi nhận giá trị trả về: tên view `String`, `ModelAndView`, `View` hay response body trực tiếp.
4. Kiểm tra model keys được truyền đến template.
5. Xem danh sách `ViewResolver` và thứ tự xử lý khi có nhiều công nghệ view.
6. Xác nhận prefix, suffix và sự tồn tại của template trong runtime classpath.
7. Quan sát exception của template engine, status code và response body.
8. Với redirect/forward, kiểm tra đường dẫn đích, context path và mapping mới.

## 15. Chọn ViewResolver hay @ResponseBody trong thiết kế thực tế?

Nên sử dụng **ViewResolver** khi ứng dụng phục vụ HTML động được render từ server, ví dụ trang quản trị, form, báo cáo, dashboard giao diện nội bộ hoặc trang có thể dùng lại nhiều fragments.

Nên sử dụng **`@RestController` / `@ResponseBody`** khi endpoint trả JSON, text hoặc dữ liệu để frontend riêng tiêu thụ, ví dụ REST API cho React, Vue, mobile application.

Hai cách có thể cùng tồn tại trong một ứng dụng Spring MVC. Phân biệt chúng theo nhu cầu response của endpoint, không phải theo URL có hoặc không có từ `api`.

Nếu chọn Spring WebFlux thay Spring MVC, cần dùng namespace và cơ chế view resolution của reactive stack; các API Servlet như `org.springframework.web.servlet.ViewResolver` không dùng trực tiếp để cấu hình WebFlux.

## 16. Checklist ghi nhớ

1. Controller `@Controller` trả `String` thường là tên view logic, không phải HTML body.
2. `DispatcherServlet` điều phối controller, model, resolver và bước render.
3. `ViewResolver` ánh xạ view name → `View`; `View` render model thành HTTP response.
4. Với Thymeleaf của Spring Boot, `"pages/welcome"` thường trỏ tới `classpath:/templates/pages/welcome.html`.
5. `spring.thymeleaf.prefix/suffix` khác `spring.mvc.view.prefix/suffix` của internal-resource/JSP resolver.
6. Nhiều resolver có thể cùng tồn tại; cần kiểm soát thứ tự, đặc biệt để `InternalResourceViewResolver` cuối.
7. `@RestController` / `@ResponseBody` sử dụng `HttpMessageConverter`, bỏ qua cơ chế view-name rendering thông thường.
8. `ModelAndView` gói dữ liệu và view name hoặc `View` cụ thể.
9. `redirect:` tạo chuyển hướng HTTP; `forward:` chuyển xử lý nội bộ qua server.
10. Kiểm thử phải bao gồm tên view, dữ liệu model và HTML thực tế ở response.

## 17. Tài liệu tham khảo

- Spring Framework — View Resolution: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html
- Spring Framework — Controller Method Return Values: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework — @ResponseBody: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html
- Spring Framework — MVC Configuration: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config.html
- Spring Boot — Customize ViewResolvers: https://docs.spring.io/spring-boot/how-to/spring-mvc.html
- Spring Boot 3.5 — Servlet Web Applications and Template Engines: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Thymeleaf — Using Thymeleaf: https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html

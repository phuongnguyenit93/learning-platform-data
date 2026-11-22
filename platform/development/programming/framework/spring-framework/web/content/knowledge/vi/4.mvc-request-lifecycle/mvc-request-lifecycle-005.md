# ModelAndView, ViewResolver và giai đoạn kết xuất giao diện trong Spring MVC

## 1. Vấn đề: Controller xử lý xong, HTML đến trình duyệt bằng cách nào?

Một HTTP request tới ứng dụng Spring MVC không kết thúc ngay khi phương thức controller trả về. Với kiểu **server-side rendered HTML**, sau khi controller lấy dữ liệu và quyết định trang cần hiển thị, framework còn phải:

1. Thu thập dữ liệu để hiển thị (**model**).
2. Xác định tên giao diện logic hoặc đối tượng giao diện (**view**).
3. Tìm công cụ/đích có thể xử lý view (**view resolution**).
4. Kết xuất view dựa trên model thành nội dung HTTP response (**rendering**).

Ba khái niệm trung tâm là **`ModelAndView`**, **`ViewResolver`** và **`View`**. Chúng kết hợp với `DispatcherServlet` để hoàn thành phần cuối của luồng MVC.

Ví dụ, trình duyệt gọi:

```http
GET /books HTTP/1.1
Host: localhost:8080
Accept: text/html
```

Controller có thể trả về tên trang `"books"` cùng model gồm tiêu đề và danh sách sách. `ViewResolver` ánh xạ `"books"` tới template như `classpath:/templates/books.html`; engine template thay các biểu thức dữ liệu và tạo HTML để gửi về browser.

**Phân biệt:** Controller trả tên `"books"` không có nghĩa response body chỉ chứa chữ `books`. Với `@Controller` và không có `@ResponseBody`, đây thường là **logical view name**. Với `@RestController` hoặc `@ResponseBody`, kết quả đi qua cơ chế ghi response body, thường **không gọi ViewResolver**.

## 2. Vị trí trong luồng xử lý MVC

```text
Client / Browser
      |
      | HTTP GET /books
      v
Servlet container (Tomcat, Jetty, ...)
      |
      v
DispatcherServlet
      |
      +--> HandlerMapping: tìm handler tương ứng URL + method
      |
      +--> HandlerAdapter: chuẩn bị tham số, gọi controller
      |         |
      |         v
      |   @Controller: xử lý nghiệp vụ, cung cấp model/view
      |         |
      |         v
      |   ModelAndView hoặc thông tin tương đương
      |
      +--> ViewResolver(s): logical name "books" -> View
      |                                           |
      |                                           v
      +-------------------------------------- View.render(...)
                                                  |
                                                  v
                                        HTML / HTTP response
                                                  |
                                                  v
                                               Browser
```

Đây là **luồng đồng bộ tiêu biểu của request tạo HTML**, đã lược bớt filter, interceptor, exception resolver, locale resolution, multipart processing và các khả năng khác. Spring MVC có nhiều kiểu return value và cơ chế bất đồng bộ; không phải request nào cũng đi qua đầy đủ bước tìm view.

Trong Spring MVC, `DispatcherServlet` là **front controller**. Nó phối hợp những thành phần chiến lược như `HandlerMapping`, `HandlerAdapter`, `HandlerExceptionResolver` và `ViewResolver`. Từ controller đến response, framework có nhiệm vụ diễn giải kiểu giá trị trả về và quyết định cách hoàn thành request.

### Quan hệ giữa các lớp

| Thành phần | Công việc | Ví dụ |
|---|---|---|
| `Model` | Chứa dữ liệu để view đọc | `pageTitle`, `books`, `user` |
| Logical view name | Tên view ở mức nghiệp vụ/UI | `"books"`, `"account/profile"` |
| `ModelAndView` | Gói view và dữ liệu model, có thể mang HTTP status | `new ModelAndView("books")` |
| `ViewResolver` | Biến logical view name thành đối tượng `View` | Thymeleaf, JSP, FreeMarker resolver |
| `View` | Kết xuất dữ liệu vào HTTP response | Thymeleaf view, JSP view, RedirectView |
| `DispatcherServlet` | Điều phối request và bước render | Front controller của Spring MVC |

`ModelAndView` không phải HTML đã render. `ViewResolver` cũng không phải template engine: resolver **chọn/giải quyết view**, còn `View` và công nghệ bên dưới mới thực hiện việc kết xuất. Có hệ thống tích hợp những vai trò này trong cùng một thư viện, nhưng về mặt khái niệm cần tách.

## 3. Model là gì?

**Model** biểu diễn các thuộc tính mà controller cung cấp cho view của một request. Trong annotated Spring MVC controller, `org.springframework.ui.Model` là interface hỗ trợ đưa cặp tên–giá trị vào model:

```java
@GetMapping("/greeting")
public String greeting(Model model) {
    model.addAttribute("name", "Lan");
    model.addAttribute("message", "Chào mừng!");
    return "greeting";
}
```

**Đoạn mã này chỉ minh họa một handler**, chưa độc lập chạy được vì thiếu class controller, imports, dependency và template. Trong view `greeting`, các thuộc tính `name`, `message` có thể được dùng để tạo nội dung giao diện.

Cần phân biệt:

- `Model` là API để thêm các thuộc tính dùng trong quá trình render.
- `ModelMap` là một triển khai kiểu map dành cho dữ liệu model.
- `Map<String, Object>` cũng có thể được Spring MVC sử dụng trong một số chữ ký controller.
- `@ModelAttribute` cho phép khai báo/khởi tạo thuộc tính model và hỗ trợ bind dữ liệu; nó không đồng nghĩa với `@RequestBody`.
- Model dùng để render **không mặc nhiên sống qua nhiều HTTP request**; redirect tạo request mới, muốn chuyển thông báo một lần có thể dùng flash attributes, muốn lưu trạng thái phiên cần cơ chế phù hợp khác.

Ví dụ biểu diễn model về mặt khái niệm:

```text
pageTitle -> "Danh mục sách"
books     -> ["Java Core", "Spring MVC"]
notice    -> "Đã lưu thành công"
```

Khi template đọc các giá trị này, nó có thể hiển thị tiêu đề, lặp qua danh sách và hiển thị thông báo. Dữ liệu model có thể là chuỗi, số, collection hoặc đối tượng nghiệp vụ/view DTO. Không nên đổ trực tiếp entity phức tạp chứa dữ liệu bí mật vào model nếu view chỉ cần vài thuộc tính cụ thể.

## 4. ModelAndView là gì?

`org.springframework.web.servlet.ModelAndView` là **đối tượng kết hợp thông tin view và model**, có thể bao gồm cả HTTP status, để Spring MVC thực hiện bước render.

Các cách tạo phổ biến:

```java
ModelAndView mav = new ModelAndView("books");
mav.addObject("pageTitle", "Danh mục sách");
mav.addObject("books", List.of("Java Core", "Spring MVC"));
return mav;
```

Hoặc truyền dữ liệu từ đầu:

```java
return new ModelAndView("books", "pageTitle", "Danh mục sách");
```

Có thể cung cấp chính một đối tượng `View` thay vì tên view, hoặc đặt status phù hợp bằng API `ModelAndView`. Tuy nhiên, trong đa số controller server-side HTML, **tên view logic + model** là cách trình bày dễ hiểu và đủ linh hoạt.

### Các thành phần bên trong

```text
ModelAndView
  ├── View name: "books"             (hoặc một đối tượng View)
  ├── Model:
  │     "pageTitle" = "Danh mục sách"
  │     "books"     = List<String>
  └── HTTP status (tùy chọn)
```

Một số method thường dùng:

| API | Tác dụng |
|---|---|
| `new ModelAndView("books")` | Tạo kết quả với logical view name |
| `addObject("key", value)` | Thêm attribute vào model |
| `addAllObjects(map)` | Thêm nhiều attributes |
| `getViewName()` | Lấy tên view nếu kết quả dùng view name |
| `getView()` | Lấy đối tượng `View` nếu được thiết lập trực tiếp |
| `getModel()` | Lấy các attributes trong model |
| `setViewName("...")` | Thay tên view |
| `setStatus(HttpStatus.OK)` | Gắn HTTP status thích hợp khi cần |

Khi controller trả `ModelAndView`, Spring MVC diễn giải nó thành view và model để phối hợp rendering. Nếu controller trả `String` cùng tham số `Model`, Spring cũng có thể tập hợp thông tin tương đương mà không yêu cầu bạn tự tạo object `ModelAndView`.

### So sánh hai cách biểu đạt

**Cách A: controller trả `ModelAndView`**

```java
@GetMapping("/books")
public ModelAndView books() {
    ModelAndView mav = new ModelAndView("books");
    mav.addObject("pageTitle", "Danh mục sách");
    mav.addObject("books", List.of("Java Core", "Spring MVC"));
    return mav;
}
```

**Cách B: controller trả tên view, model qua tham số**

```java
@GetMapping("/books")
public String books(Model model) {
    model.addAttribute("pageTitle", "Danh mục sách");
    model.addAttribute("books", List.of("Java Core", "Spring MVC"));
    return "books";
}
```

Đây là hai **cách thay thế nhau** để khai báo endpoint và không được đặt đồng thời hai handler `GET /books` trong cùng ứng dụng. Cả hai đoạn là ví dụ method rời, cần nằm trong một `@Controller` có imports và template tương ứng.

Khi logic chỉ thêm vài attribute và chọn một trang, `String + Model` thường gọn hơn. `ModelAndView` thuận tiện khi muốn truyền view và model thành một giá trị, chọn động nhiều view hoặc làm việc với API trả `ModelAndView`.

## 5. ViewResolver: đổi tên logic thành View

Interface `org.springframework.web.servlet.ViewResolver` có phương thức cốt lõi về mặt ý nghĩa:

```java
View resolveViewName(String viewName, Locale locale) throws Exception;
```

Resolver nhận tên `viewName`, locale và tìm cách xác định đối tượng `View` phù hợp. Khi không giải quyết được, theo hợp đồng nó có thể trả `null`, cho phép các resolver khác thử tiếp.

Ví dụ:

```text
Controller trả: "books"
        |
        v
ThymeleafViewResolver
        |
        v
Thymeleaf view "books"
        |
        v
Template: classpath:/templates/books.html
```

**Đường dẫn thực tế phụ thuộc engine và cấu hình.** Không phải mọi `ViewResolver` đều nối tiền tố/hậu tố, và không phải mọi view là file HTML. Một số view đại diện JSP, redirect, tài nguyên hiển thị theo loại nội dung khác, hoặc một bean được cung cấp sẵn.

### 5.1. Các ViewResolver thường gặp

| Resolver | Tình huống sử dụng | Ghi chú |
|---|---|---|
| `ThymeleafViewResolver` | Render template Thymeleaf | Tích hợp template engine của Thymeleaf |
| `InternalResourceViewResolver` | JSP và Servlet forwarding | Nên đặt cuối chuỗi resolver |
| `FreeMarkerViewResolver` | Render FreeMarker | Phụ thuộc cấu hình FreeMarker |
| `BeanNameViewResolver` | Tìm bean `View` theo tên | Hữu ích cho view tùy biến |
| `ContentNegotiatingViewResolver` | Chọn view tương thích với media type client chấp nhận | Kết hợp/ủy quyền các resolver khác |
| `UrlBasedViewResolver` | Tên view ánh xạ theo URL quy ước | Lớp nền cho một số resolver |

**Lưu ý về độ ưu tiên:** Có thể khai báo nhiều resolver và sắp xếp bằng thuộc tính `order` (giá trị order nhỏ hơn được xét sớm hơn). Resolver đầu tiên tìm ra view phù hợp có thể kết thúc quá trình, vì vậy order sai có thể khiến engine mong muốn không được chọn.

`InternalResourceViewResolver` khó xác định JSP đích có tồn tại hay không trước khi forward request, nên trong cấu hình nhiều resolver thường cần đặt nó **sau cùng**. Nếu đặt trước, nó có thể nhận hầu hết view name và cản resolver tiếp theo.

### 5.2. ViewResolver không phải lúc nào cũng cần cấu hình thủ công

Trong Spring Boot MVC khi thêm `spring-boot-starter-thymeleaf`, Boot thường tự cấu hình Thymeleaf view resolver và tìm template dưới `classpath:/templates/`. Tên view `"books"` mặc định tương ứng `templates/books.html`.

Tùy cấu hình, có thể sử dụng các property như:

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.cache=false
```

Các giá trị prefix/suffix trên là mặc định phổ biến của Thymeleaf trong Boot. Thiết lập `cache=false` hữu ích khi sửa template trong môi trường phát triển nhưng thường không nên tắt cache tùy tiện ở production. **Cache của view resolver và cache của template engine không nhất thiết là cùng một cơ chế**.

Spring Framework thuần không có Boot auto-configuration; bạn phải cung cấp cấu hình MVC/template cần thiết. Không nên lấy cấu hình Boot rồi giả định nó tự hoạt động trong một WAR Spring MVC thuần.

### 5.3. Locale và content negotiation

`ViewResolver` nhận `Locale`, nên một số resolver/template có thể lựa chọn nội dung phù hợp ngôn ngữ hoặc khu vực. Locale còn có thể ảnh hưởng cách format ngày/số và message bundle trong template; không nên nhầm locale với đường dẫn view.

Khi có nhiều representation, `ContentNegotiatingViewResolver` có thể kết hợp các resolver và dùng media type yêu cầu (ví dụ header `Accept`) để chọn view tương thích. Tuy nhiên, trả JSON từ `@ResponseBody` thông thường đi qua `HttpMessageConverter` và **không cần ép JSON thành một template view**.

## 6. Bước kết xuất giao diện thực sự xảy ra thế nào?

Sau khi chọn được `View`, `DispatcherServlet` gọi chức năng render của view, về mặt contract có dạng:

```java
void render(
        Map<String, ?> model,
        HttpServletRequest request,
        HttpServletResponse response
) throws Exception;
```

Đây là **chữ ký API để giải thích**, không phải chương trình Java độc lập. Tên import `HttpServletRequest`/`HttpServletResponse` tương ứng Jakarta Servlet trong Spring Framework 6+.

Từng bước điển hình khi render Thymeleaf:

1. `View` nhận model và request/response.
2. Engine tìm/đọc template có tên `books` theo prefix/suffix.
3. Các biểu thức trong template truy cập model (`pageTitle`, `books`).
4. Engine tạo markup HTML, xử lý điều kiện, vòng lặp, fragment, liên kết và escaped output theo cú pháp của engine.
5. Spring và Servlet response ghi nội dung, status và các header thích hợp, ví dụ `Content-Type: text/html;charset=UTF-8` khi được cấu hình.
6. Servlet container gửi các byte response tới client; trình duyệt phân tích HTML và tự thực hiện render giao diện trên màn hình.

**Hai kiểu “render” cần phân biệt:** Spring render **nội dung HTML ở server**; trình duyệt render **giao diện trực quan** từ HTML/CSS/JS ở client. `View.render` không trực tiếp vẽ pixel trên màn hình người dùng.

Ví dụ template Thymeleaf:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="${pageTitle}">Tiêu đề tạm</title>
</head>
<body>
    <h1 th:text="${pageTitle}">Tiêu đề tạm</h1>
    <ul>
        <li th:each="book : ${books}" th:text="${book}">Sách</li>
    </ul>
</body>
</html>
```

Nếu model có `pageTitle="Danh mục sách"` và `books=["Java Core", "Spring MVC"]`, browser nhận một tài liệu HTML chứa tiêu đề tương ứng và hai phần tử danh sách. Trong HTML sau render, thuộc tính `th:text` và `th:each` đã được engine xử lý; đây không còn là template gốc.

### Vì sao cần quan tâm HTML escaping?

Thymeleaf `th:text` thoát các ký tự có ý nghĩa đặc biệt trong HTML. Ví dụ nếu tên sách chứa `<script>`, dùng `th:text` sẽ hiển thị như văn bản thay vì chèn một thẻ script thực thi. Ngược lại, `th:utext` cho phép HTML không escape và **rủi ro XSS** nếu render dữ liệu không tin cậy mà chưa được kiểm soát/khử độc đúng cách.

Không dùng việc “template tự escape” thay cho authentication, authorization, input validation và chính sách bảo mật ứng dụng. Dữ liệu model chỉ nên chứa những thông tin được phép hiển thị; server-side rendering vẫn có thể làm rò rỉ dữ liệu nếu controller đổ thông tin nhạy cảm vào template.

## 7. Các kiểu giá trị trả về của Controller: khi nào có ViewResolver?

Trong Spring MVC, cách diễn giải giá trị trả về phụ thuộc **annotation và return-value handler**.

| Controller trả | Spring xử lý thông thường | Có dùng ViewResolver? |
|---|---|---|
| `@Controller` trả `String "books"` | Tên view logic, kết hợp model hiện có | Có |
| `@Controller` trả `ModelAndView("books")` | View + model (+ status tùy chọn) | Có nếu cung cấp view name |
| `@Controller` trả đối tượng `View` | Dùng trực tiếp đối tượng view với model | Không cần giải tên view |
| `@Controller` trả `Model`/`Map` | Thêm attributes; có thể suy ra tên view | Có nếu cần render view |
| `@Controller` + `@ResponseBody` | Ghi dữ liệu bằng `HttpMessageConverter` | Không |
| `@RestController` | Mặc định ghi kết quả như response body | Không trong trường hợp thông thường |
| `ResponseEntity<T>` | Chỉ định status, header và body | Không theo đường view thông thường |
| `"redirect:/books"` | Chọn redirect view / HTTP redirect | Có thể dùng chiến lược nhận prefix redirect |
| `"forward:/books"` | Server-side forward đến tài nguyên đích | Phụ thuộc resolver hỗ trợ prefix forward |

**Ví dụ gây nhầm lẫn:**

```java
@Controller
class ExampleController {
    @GetMapping("/a")
    public String a() {
        return "home";            // logical view name: home
    }

    @ResponseBody
    @GetMapping("/b")
    public String b() {
        return "home";            // response body văn bản: home
    }
}
```

Hai method trên được đặt trong một class minh họa, giả sử cấu hình MVC và view `home` tồn tại. Một giá trị Java `String` như nhau có thể dẫn đến hai luồng HTTP khác nhau do annotation quyết định.

**`@RestController` tương đương sự kết hợp ý nghĩa của `@Controller` và `@ResponseBody` ở cấp class.** Nếu muốn render template HTML server-side, lựa chọn tự nhiên là `@Controller` và trả view name/`ModelAndView`, thay vì `@RestController` trả `"books"`.

## 8. Ví dụ hoàn chỉnh: Spring Boot MVC + Thymeleaf

Ví dụ chạy trên **Java 17+**, Maven và Spring Boot 3.3.5 (một phiên bản cố định để minh họa API, không tuyên bố là bản mới nhất). Khi xây dựng sản phẩm mới, cần chọn bản Spring Boot còn được hỗ trợ phù hợp môi trường. Ứng dụng sử dụng `spring-boot-starter-web` để xử lý HTTP MVC và `spring-boot-starter-thymeleaf` để render HTML.

### 8.1. Cấu trúc dự án

```text
mvc-view-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/views/
    │   │   ├── MvcViewApplication.java
    │   │   ├── CatalogService.java
    │   │   └── CatalogController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/books.html
    └── test/
        └── java/com/example/views/
            └── CatalogControllerTest.java
```

### 8.2. Maven dependencies

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>mvc-view-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
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

Starter Thymeleaf cung cấp bộ tích hợp engine với Spring MVC. Boot cung cấp `DispatcherServlet`, thiết lập resolver tương ứng và tìm file HTML trong thư mục template mặc định; không cần tự khai báo `InternalResourceViewResolver` cho ví dụ này.

### 8.3. Khởi tạo ứng dụng

Tạo `MvcViewApplication.java`:

```java
package com.example.views;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcViewApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcViewApplication.class, args);
    }
}
```

### 8.4. Service cung cấp dữ liệu

Tạo `CatalogService.java`:

```java
package com.example.views;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    public List<String> listTitles() {
        return List.of("Java Core", "Spring MVC");
    }
}
```

Service dùng danh sách bất biến để ví dụ có output xác định và không cần database. Trong ứng dụng thật, service có thể lấy thông tin từ repository hoặc dịch vụ bên ngoài, nhưng controller vẫn chỉ nên tập trung chuẩn bị dữ liệu cần cho view.

### 8.5. Controller minh họa ba đường xử lý

Tạo `CatalogController.java`:

```java
package com.example.views;

import java.util.List;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.ModelAndView;

@Controller
public class CatalogController {
    private final CatalogService catalog;

    public CatalogController(CatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/books")
    public ModelAndView showBooks() {
        ModelAndView mav = new ModelAndView("books");
        mav.addObject("pageTitle", "Danh mục sách");
        mav.addObject("books", catalog.listTitles());
        return mav;
    }

    @GetMapping("/books/alternative")
    public String showBooksAlternative(Model model) {
        model.addAttribute("pageTitle", "Danh mục sách");
        model.addAttribute("books", catalog.listTitles());
        return "books";
    }

    @GetMapping("/books/json")
    @ResponseBody
    public List<String> booksAsJson() {
        return catalog.listTitles();
    }

    @GetMapping("/books/go")
    public String navigateToBooks() {
        return "redirect:/books";
    }
}
```

Bốn endpoint có ý nghĩa khác nhau:

- `GET /books`: tạo `ModelAndView` với view name `books` và model; Spring tìm Thymeleaf view để render.
- `GET /books/alternative`: kết quả HTML tương đương, nhưng controller trả `String` view name và dùng tham số `Model`.
- `GET /books/json`: `@ResponseBody` khiến Spring dùng HTTP message conversion để trả JSON; **không render books.html**.
- `GET /books/go`: tạo HTTP redirect tới `/books`; trình duyệt gửi request mới tới đích.

`List<String>` trên endpoint JSON được chuyển thành JSON qua Jackson trong cấu hình `spring-boot-starter-web`. Ứng dụng không trả các object service hoặc engine template cho client.

### 8.6. Tạo template Thymeleaf

Tạo `src/main/resources/templates/books.html`:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="${pageTitle}">Tiêu đề mặc định</title>
</head>
<body>
    <h1 th:text="${pageTitle}">Tiêu đề mặc định</h1>
    <ul>
        <li th:each="book : ${books}" th:text="${book}">Tên sách</li>
    </ul>
    <a th:href="@{/books/alternative}">Cách viết bằng Model</a>
</body>
</html>
```

Ở bước render, Thymeleaf:

1. Nhận `pageTitle` và `books` từ model.
2. Thay `th:text` bằng dữ liệu văn bản đã escape theo ngữ cảnh HTML.
3. Lặp qua danh sách `books` bằng `th:each` để tạo hai phần tử `li`.
4. Xây dựng link với `th:href`.
5. Tạo response HTML cho browser.

File `books.html` là template nguồn; lúc chạy browser không cần hiểu cú pháp `th:...`. Engine ở server đã xử lý các thuộc tính đó.

### 8.7. Cấu hình và chạy

Trong `src/main/resources/application.properties`, có thể đặt:

```properties
server.port=8080
spring.thymeleaf.cache=false
```

`cache=false` là tiện ích lúc phát triển để quan sát thay đổi template. Không thêm `@EnableWebMvc` vào ví dụ Boot nếu không có yêu cầu thay thế một phần cấu hình MVC tự động.

Chạy từ thư mục dự án có `pom.xml`:

```bash
mvn spring-boot:run
```

Hoặc xây dựng JAR trước rồi chạy:

```bash
mvn clean package
java -jar target/mvc-view-demo-1.0.0.jar
```

Giả sử server chạy bình thường trên `localhost:8080`, thử:

```bash
curl -i "http://localhost:8080/books"
```

Response dự kiến có status `200 OK`, `Content-Type` tương thích `text/html` và HTML chứa tiêu đề **Danh mục sách**, cùng hai dòng **Java Core** và **Spring MVC**. Không cần khẳng định mọi byte response cố định vì formatting và header phụ thuộc phiên bản/configuration.

```bash
curl -s "http://localhost:8080/books/json"
```

Body JSON dự kiến chính xác khi dùng danh sách trong ví dụ:

```json
["Java Core","Spring MVC"]
```

```bash
curl -i "http://localhost:8080/books/go"
```

Kết quả dự kiến: HTTP `302 Found` với header `Location` trỏ tới `/books`; có thể là URL tuyệt đối hoặc dạng phù hợp cấu hình runtime. `curl` mặc định **không tự theo redirect** nếu không thêm `-L`.

```bash
curl -L "http://localhost:8080/books/go"
```

Khi theo redirect, cuối cùng client nhận HTML của trang `/books`.

### 8.8. Kiểm thử cả view name, model và HTML

Tạo `src/test/java/com/example/views/CatalogControllerTest.java`:

```java
package com.example.views;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CatalogControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rendersViewFromModelAndView() throws Exception {
        mvc.perform(get("/books"))
           .andExpect(status().isOk())
           .andExpect(view().name("books"))
           .andExpect(model().attribute("pageTitle", "Danh mục sách"))
           .andExpect(model().attribute(
                   "books", List.of("Java Core", "Spring MVC")))
           .andExpect(content().string(containsString("Java Core")))
           .andExpect(content().string(containsString("Spring MVC")));
    }

    @Test
    void writesJsonWithoutTemplateRendering() throws Exception {
        mvc.perform(get("/books/json"))
           .andExpect(status().isOk())
           .andExpect(content().json(
                   "[\"Java Core\",\"Spring MVC\"]"));
    }

    @Test
    void redirectsToBooks() throws Exception {
        mvc.perform(get("/books/go"))
           .andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrl("/books"));
    }
}
```

Chạy:

```bash
mvn test
```

Các assertion kiểm tra **kết quả có ý nghĩa của từng giai đoạn**: handler chọn đúng view `books`, model chứa hai thuộc tính cần thiết, Thymeleaf thực sự render HTML có nội dung, endpoint JSON tạo JSON, và redirect sinh URL đích. Đây là kiểm thử Spring Boot integration với `MockMvc` chạy qua pipeline MVC mà không cần mở cổng mạng thực. Khi thay đổi context path, security hay template, kỳ vọng test cần cập nhật tương ứng.

## 9. Redirect và forward: đều có thể trả view name đặc biệt

Một `@Controller` có thể trả logical view name bắt đầu bằng `redirect:` hoặc `forward:` tùy cấu hình MVC.

### 9.1. Redirect: client nhận lệnh đi tới URL khác

```java
@GetMapping("/old")
public String oldPage() {
    return "redirect:/books";
}
```

Đây là **method minh họa**; muốn chạy phải đặt trong một controller được đăng ký. Spring thường dùng một `RedirectView` tương đương để tạo phản hồi chuyển hướng. Client nhận mã 3xx và `Location`, sau đó gửi **một request mới** đến URL đích. URL hiển thị trong thanh địa chỉ thường thay đổi khi browser đi theo redirect.

Redirect đặc biệt hữu ích cho mẫu **Post/Redirect/Get (PRG)**: sau khi server xử lý form POST thành công, trả redirect để browser tải trang kết quả bằng GET, giảm nguy cơ người dùng refresh rồi vô tình gửi lại POST.

Ví dụ method mô tả PRG với flash message:

```java
@PostMapping("/orders")
public String submitOrder(
        @RequestParam String title,
        RedirectAttributes redirectAttributes) {
    // Xử lý tạo đơn qua service và kiểm tra lỗi ở đây.
    redirectAttributes.addFlashAttribute(
            "notice", "Đã nhận đơn: " + title);
    return "redirect:/orders";
}
```

Đây là **mảnh minh họa**, không phải endpoint sản xuất hoàn chỉnh: thiếu class, imports, service, kiểm tra đầu vào, authentication/CSRF, lưu đơn và đích `GET /orders`. `RedirectAttributes.addFlashAttribute` cho phép chuyển dữ liệu tạm thời tới request sau redirect mà không phải đưa thông báo vào query string. Flash attributes thường lưu tạm qua cơ chế session/FlashMap; các request đồng thời có thể tạo tình huống cần xử lý cẩn thận.

Không mặc nhiên dùng model của request trước cho request sau; sau redirect cần load dữ liệu lại hoặc sử dụng flash/session theo thiết kế.

### 9.2. Forward: server chuyển tiếp nội bộ

```java
@GetMapping("/legacy")
public String legacyPage() {
    return "forward:/books";
}
```

Đây cũng là method minh họa. Forward dùng cơ chế `RequestDispatcher.forward()` trong Servlet container để chuyển xử lý **nội bộ phía server**, thường giữ cùng request/response và browser không thấy một redirect HTTP 3xx do controller này sinh ra. Forward có các điều kiện/ràng buộc do Servlet API áp dụng, ví dụ response đã commit thường không thể forward.

Không xem redirect và forward là hai cách hoàn toàn tương đương. Redirect tạo request mới, có thể đổi URL và phù hợp PRG; forward nằm trong request hiện tại. Hãy kiểm tra view resolver và servlet mapping nếu dùng tiền tố `forward:`.

## 10. Cách giai đoạn ViewResolver tương tác với lỗi

Một số tình huống khác nhau có thể tạo ra kết quả nhìn giống nhau ở phía browser:

| Hiện tượng | Giai đoạn nghi ngờ | Gợi ý kiểm tra |
|---|---|---|
| `404 Not Found` khi vào `/books` | Mapping handler hoặc URL | Kiểm tra `@GetMapping`, context path, servlet mapping |
| Controller chạy nhưng không tìm được template | Resolve/render view | Kiểm tra view name, `templates/`, suffix, starter |
| `500 Internal Server Error` với lỗi xử lý template | Render | Kiểm tra expression, model attribute, lỗi template |
| Browser hiển thị nguyên chữ `books` | Return value ghi body | Có nhầm `@RestController`/`@ResponseBody` không? |
| Model có dữ liệu nhưng trang trống | Template expression / binding | Kiểm tra tên key và cách truy cập trong template |
| Nhiều ViewResolver, trang bị chọn sai | Chuỗi resolver | Kiểm tra `order` và resolver nhận view quá rộng |
| JSP không tìm thấy dù tên view đúng | JSP path / resolver / packaging | Kiểm tra `InternalResourceViewResolver` và WAR/JAR |
| Redirect làm lộ dữ liệu ở URL | Redirect attributes | Dùng `RedirectAttributes` chọn dữ liệu công khai; flash cho thông báo tạm |

### 10.1. Lỗi view name sai đường dẫn

Ví dụ controller trả `"book-list"`, nhưng tệp là `templates/books.html`. Nếu không có cấu hình ánh xạ đặc biệt, resolver không tìm được template `book-list`. Tạo đúng tên template hoặc sửa logic chọn view cho khớp, đừng chữa bằng cách đổi ngẫu nhiên nhiều property.

### 10.2. Trả nhầm `@RestController`

```java
@RestController
class WrongPageController {
    @GetMapping("/bad-page")
    public String page() {
        return "books";
    }
}
```

Ví dụ này trả response body chữ `books`, **không** yêu cầu Thymeleaf tìm `books.html`. Để server-side HTML, dùng `@Controller` phù hợp và trả tên view; để API trả dữ liệu, giữ `@RestController`.

### 10.3. Trộn web templates với `@ResponseBody`

Nếu đặt `@ResponseBody` lên method trả `ModelAndView`, Spring có thể cố xử lý chính object như body thay vì diễn giải nó như kết quả MVC render view. Không dùng sự kết hợp này để hiển thị HTML; chọn một cơ chế response phù hợp.

### 10.4. JSP và Spring Boot JAR

JSP có yêu cầu đóng gói, container và cấu hình khác Thymeleaf. Spring Boot tài liệu hóa hạn chế khi dùng JSP với embedded Servlet container và executable JAR. Đừng sao chép máy móc cấu hình `InternalResourceViewResolver` từ dự án WAR truyền thống sang Boot JAR; nếu cần JSP, đánh giá cấu trúc triển khai cụ thể. Với ví dụ nhập môn Boot MVC, Thymeleaf thường dễ thực hành hơn.

### 10.5. Dữ liệu không được escape hoặc hiển thị dữ liệu nhạy cảm

Model không phải cơ chế phân quyền. Bảo đảm service/controller kiểm soát dữ liệu được đưa ra view và sử dụng escaping/encoding phù hợp ngữ cảnh. Với Thymeleaf HTML, ưu tiên `th:text` cho text đầu vào thay vì kết xuất HTML không kiểm soát.

## 11. Quan sát và kiểm chứng pipeline rendering

Có thể debug theo chuỗi câu hỏi:

1. **Request có vào đúng `DispatcherServlet` không?** Xem URL, phương thức HTTP và log request mapping.
2. **Controller nào được chọn?** Kiểm tra handler mapping có đúng path/method không.
3. **Controller trả giá trị gì?** `String` view name, `ModelAndView`, `ResponseEntity` hay `@ResponseBody`?
4. **Model có đủ các attribute cần thiết không?** Kiểm tra key, kiểu dữ liệu và giá trị.
5. **Resolver nào xử lý view?** Kiểm tra engine/starter, prefix, suffix, thứ tự resolver và lỗi tìm template.
6. **View render thành gì?** Kiểm tra HTML response, status, `Content-Type`, đặc biệt lỗi expression.
7. **Browser hiển thị khác response?** Kiểm tra CSS, JavaScript, browser cache và công cụ Developer Tools.

Trong môi trường học tập, có thể bật logging Spring MVC chọn lọc để quan sát mapping và view resolution, nhưng không nên log tràn lan dữ liệu người dùng hoặc request body nhạy cảm. Khi debugging, so sánh **HTML ở tab Network → Response** với **DOM sau khi JavaScript chạy** để phân biệt lỗi server template và lỗi client rendering.

Cần nhớ rằng view resolution có thể bị **bỏ qua hoàn toàn** nếu response đã được handler xử lý (ví dụ `@ResponseBody`, `ResponseEntity`, streaming) hoặc controller thực hiện redirect. Không thấy log Thymeleaf trong API JSON là hành vi bình thường.

## 12. Vấn đề thiết kế: ModelAndView có phải lúc nào cũng nên dùng?

Không bắt buộc. Trong annotated Spring MVC, chọn cách thể hiện phù hợp với nhiệm vụ:

- Khi view cố định và chỉ có ít dữ liệu: `String` + `Model` thường ngắn gọn.
- Khi muốn gói model/view thành một object hoặc chọn view động: `ModelAndView` rõ ràng.
- Khi controller tạo response JSON/REST: `@RestController`/`@ResponseBody`/`ResponseEntity` thường phù hợp hơn.
- Khi cần phát một file/stream lớn: cân nhắc cơ chế response hoặc streaming phù hợp, tránh ép thành HTML template.
- Khi cần redirect sau POST: return `redirect:` hoặc `RedirectView` kết hợp `RedirectAttributes`.
- Khi giao diện là SPA được phục vụ tĩnh hoặc qua CDN: Spring MVC có thể chỉ làm backend API; không bắt buộc render template phía server.

Đừng đẩy truy vấn database, gọi dịch vụ ngoài, cập nhật nghiệp vụ hay điều kiện phân quyền phức tạp vào template. Controller nên phối hợp, service xử lý nghiệp vụ, model chuẩn bị dữ liệu trình bày, view chỉ render. Sự phân chia này làm code dễ kiểm thử hơn và giảm lỗi bảo mật.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Controller `@Controller` trả `"profile"` và thêm `user` vào `Model`. Trình duyệt có nhận đúng chuỗi `profile` làm body không?  
**Giải đáp:** Thường không. Spring hiểu chuỗi đó là logical view name, gọi view resolution và render bằng model. Body cuối cùng do view tạo ra.

**Câu 2.** `ModelAndView` có tự biên dịch Thymeleaf template không?  
**Giải đáp:** Không. Nó mang thông tin view và model; `ViewResolver` chọn `View`, sau đó view cùng template engine thực hiện rendering.

**Câu 3.** `@RestController` trả `"books"` thì `books.html` có được render không?  
**Giải đáp:** Không theo cơ chế mặc định; `@RestController` áp dụng `@ResponseBody`, nên chuỗi được ghi vào response body.

**Câu 4.** `GET /books` trả 404, vậy chắc chắn `ViewResolver` sai?  
**Giải đáp:** Không. Có thể request không khớp handler/mapping. Phải kiểm tra routing trước rồi mới đến view resolution.

**Câu 5.** Spring Boot có Thymeleaf starter thì có cần tự tạo một `InternalResourceViewResolver` cho `books.html` không?  
**Giải đáp:** Không. Với thiết lập Thymeleaf mặc định, Boot tự cấu hình resolver phù hợp và nhận template trong `src/main/resources/templates`.

**Câu 6.** `redirect:/books` và `forward:/books` khác nhau cốt lõi thế nào?  
**Giải đáp:** Redirect phản hồi yêu cầu client gửi request mới tới URL đích; forward chuyển request nội bộ trong server khi điều kiện Servlet cho phép.

**Câu 7.** Dữ liệu của `Model` trong request POST có tự còn trong `Model` sau redirect không?  
**Giải đáp:** Không mặc định. Có thể dùng flash attributes để chuyển thông báo tạm thời hoặc nạp lại dữ liệu ở request GET đích.

**Câu 8.** Có thể đặt `InternalResourceViewResolver` ở đầu chuỗi nhiều resolver không?  
**Giải đáp:** Không nên. JSP resolver thường không thể biết chắc tài nguyên có tồn tại trước khi forward, nên nên được đặt cuối để các resolver chuyên biệt có cơ hội xử lý.

## 14. Tài liệu tham khảo chính thức

1. [Spring Framework — DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html): front controller và chiến lược MVC.
2. [Spring Framework — View Resolution](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html): `ViewResolver`, `View`, chuỗi resolver, redirect và forward.
3. [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): các kiểu giá trị controller được Spring MVC hỗ trợ.
4. [Spring Framework — Redirect Attributes / Flash Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html): chuyển dữ liệu khi redirect.
5. [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): auto-configuration của template engines và vị trí template trong Boot.

**Ghi nhớ:** Trong request render HTML phía server, controller chuẩn bị **model** và chỉ định **view**; `ModelAndView` có thể gói hai thứ đó, `ViewResolver` tìm đối tượng `View`, và `View.render` tạo HTTP response. Với `@ResponseBody`/`@RestController`, Spring ghi dữ liệu trực tiếp qua cơ chế message conversion và thường không đi qua view resolver.

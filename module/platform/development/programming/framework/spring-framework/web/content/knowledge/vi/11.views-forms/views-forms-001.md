# Model, ModelMap, ModelAndView và tên view logic trong Spring MVC

## 1. Mục tiêu bài học

Khi xây dựng giao diện HTML bằng **Spring MVC**, controller thường không trả trực tiếp HTML. Nó chuẩn bị dữ liệu cho giao diện (**model**) và chỉ ra giao diện cần hiển thị (**view**). Spring sau đó dùng **ViewResolver** để chọn view thực tế (ví dụ một template Thymeleaf) và render response.

Bài học giúp bạn:

1. Phân biệt **`Model`**, **`ModelMap`**, **`ModelAndView`** về kiểu Java, khả năng chứa dữ liệu và cách chỉ định view.
2. Hiểu **tên view logic** như `"products/detail"` được resolve thành template thực tế như `classpath:/templates/products/detail.html`.
3. Chọn cách viết controller hợp lý: truyền `Model`/`ModelMap` làm tham số rồi trả `String`, hoặc trả `ModelAndView`.
4. Hiểu tên view mặc định, `redirect:`, `forward:`, `@ModelAttribute` và dữ liệu form được đưa vào model.
5. Nhận ra khi `String` bị diễn giải là **view name** và khi nó được gửi thành **response body** dưới `@ResponseBody`/`@RestController`.
6. Viết ứng dụng Java 17+ / Spring Boot 3.x với template Thymeleaf, form và kiểm thử MockMvc.

**Phạm vi:** Spring Framework 6.x, Spring Boot 3.x, Spring MVC sử dụng Servlet stack và server-rendered HTML. Spring WebFlux và SPA frontend có cơ chế render/truyền dữ liệu riêng. Tên view và data binding vẫn là kiến thức hữu ích khi ứng dụng kết hợp giao diện HTML với REST API.

## 2. Model và View là hai vai trò khác nhau

Một trang HTML hiển thị sản phẩm có thể cần dữ liệu:

~~~json
{"id":101,"name":"Sách Spring MVC","price":120000}
~~~

Với Spring MVC server-rendered, controller đưa dữ liệu đó vào **model**, đặt tên **view**, rồi Spring phối hợp cả hai để render HTML:

~~~mermaid
flowchart TD
    A[HTTP GET /products/101] --> B[DispatcherServlet]
    B --> C[Controller]
    C --> D[Model: product]
    C --> E[Logical view: products/detail]
    D --> F[ViewResolver]
    E --> F
    F --> G[Template: products/detail.html]
    G --> H[HTML response]
~~~

- **Model** là tập các **attribute theo tên** để view sử dụng. Model không phải entity/database model theo nghĩa ORM, cũng không tự lưu vào session hoặc database.
- **View** là cách render response, ví dụ Thymeleaf template, JSP hoặc một `View` implementation khác.
- **Tên view logic** (logical view name) là định danh như `"products/detail"`, chưa nhất thiết là một đường dẫn vật lý.
- **ViewResolver** tìm một `View` phù hợp dựa trên tên logic. Khi dùng Thymeleaf mặc định trong Spring Boot 3.x, tên `"products/detail"` thường tương ứng `src/main/resources/templates/products/detail.html`.
- View phối hợp model để tạo HTML trả cho trình duyệt. Dữ liệu trong model có phạm vi thông thường của request xử lý đó; không coi nó là dữ liệu lưu trữ vĩnh viễn.

Điểm dễ nhầm: Trong Spring MVC, `model.addAttribute("product", product)` **không gửi JSON** cho client. Controller cần trả một view name hoặc một view object; quá trình render template sau đó mới tạo response body HTML. Với `@RestController`, kết quả trả về thường được chuyển trực tiếp thành body thông qua `HttpMessageConverter`, không có bước tìm template.

## 3. So sánh `Model`, `ModelMap`, `ModelAndView`

| Tiêu chí | `Model` | `ModelMap` | `ModelAndView` |
| --- | --- | --- | --- |
| Package | `org.springframework.ui.Model` | `org.springframework.ui.ModelMap` | `org.springframework.web.servlet.ModelAndView` |
| Kiểu Java | **Interface** | **Class** kế thừa `LinkedHashMap<String, Object>` | **Class** gộp model và view |
| Nhiệm vụ chính | Thêm/đọc attribute của model | Model theo phong cách Map | Chỉ định view và kèm model trong cùng kết quả |
| API thêm dữ liệu | `addAttribute(...)`, `addAllAttributes(...)`, `asMap()` | `addAttribute(...)`, `put(...)`, `get(...)` | `addObject(...)`, `addAllObjects(...)` |
| Là tham số handler | Có | Có | Không phổ biến như tham số, thường là **return value** |
| Thường trả từ handler | `String` view name hoặc chính `Model` | `String` view name hoặc chính `ModelMap` | `ModelAndView` |
| View name đi kèm trong object? | Không | Không | Có (`setViewName`, constructor) |
| Khi nên chọn | Hầu hết handler HTML thông thường | Khi cần thao tác theo API Map | Khi muốn trả model + view + status trong một object |

`Model` và `ModelMap` là **hai cách truy cập model của Spring MVC**, không phải hai kho dữ liệu tách biệt. Trong các handler MVC bình thường, Spring cung cấp object model dùng cho request, còn `ModelAndView` là **giá trị trả về mang cả thông tin view và model**. Không tạo ra ba cách truyền dữ liệu khác nhau đến browser.

**Quy tắc chọn nhanh:** nếu handler chỉ cần thêm vài attribute rồi hiển thị template, dùng `Model` làm tham số và trả `String` tên view. Nếu cần API `Map`, có thể nhận `ModelMap`. Nếu muốn xây một object biểu diễn đồng thời view, model và có thể cả status, trả `ModelAndView`.

## 4. `Model`: giao diện làm việc trực tiếp với attribute

Mẫu phổ biến nhất trong controller dùng Thymeleaf:

~~~java
@Controller
@RequestMapping("/products")
public class ProductController {

    @GetMapping("/{id}")
    public String detail(@PathVariable long id, Model model) {
        ProductDto product = productService.findById(id);
        model.addAttribute("product", product);
        model.addAttribute("pageTitle", "Thông tin sản phẩm");
        return "products/detail";
    }
}
~~~

**Đây là đoạn minh họa bên trong một controller**, chưa là chương trình độc lập; `ProductDto` và `productService` cần được định nghĩa và inject. Những điểm đáng chú ý:

- `Model` **là interface**; Spring cung cấp instance cho method. Không cần tự tạo `new Model()`.
- `model.addAttribute("product", product)` tạo attribute với key `product`; view Thymeleaf sẽ tham chiếu bằng `${product}`.
- `return "products/detail"` là **tên view logic**, không phải JSON và không phải tên class Java.
- Spring Boot + Thymeleaf mặc định tìm template tương ứng ở `classpath:/templates/products/detail.html` nếu template engine được cấu hình.
- Controller phải xử lý trường hợp `findById` không thấy sản phẩm, ví dụ ném exception được ánh xạ sang 404 hoặc trả trang lỗi thích hợp. Ví dụ này tập trung vào luồng model/view.

Các method thường dùng của `Model`:

~~~java
model.addAttribute("title", "Danh sách sản phẩm");
model.addAttribute("count", 3);
model.addAttribute("items", items);
model.addAllAttributes(Map.of("category", "books", "sort", "name"));
Map<String, Object> snapshot = model.asMap();
~~~

Đây là các câu lệnh minh họa đặt trong handler có biến `model` và `items`. Tham chiếu được dùng trong view bằng tên attribute. Dùng `addAttribute(String, Object)` để tránh nhầm tên quy ước khi thêm object không nêu rõ key.

`Model` **không chứa view name**. Return value hoặc cơ chế tên view mặc định quyết định view cần render.

## 5. `ModelMap`: dùng model theo phong cách `Map`

`ModelMap` là class kế thừa `LinkedHashMap<String, Object>`, có cả API của Map và các method trợ giúp cho model:

~~~java
@GetMapping("/summary")
public String summary(ModelMap model) {
    model.put("pageTitle", "Tổng quan");
    model.addAttribute("total", 3);
    return "products/summary";
}
~~~

Đây là handler minh họa trong `@Controller`; cần import `ModelMap`. Trong template `products/summary.html`, hai attribute có tên `pageTitle` và `total` đều có thể được sử dụng.

Ví dụ truy xuất:

~~~java
Object total = model.get("total");
boolean contains = model.containsKey("pageTitle");
Map<String, Object> copied = new LinkedHashMap<>(model);
~~~

Đây là các câu lệnh minh họa trong cùng method với `ModelMap model`; cần import `Map` và `LinkedHashMap`. Khi bạn không cần `put`, `get`, `containsKey`, interface `Model` thường rõ ý định hơn. Tránh thêm vào model những entity nhạy cảm, access token hoặc object có đồ thị rất lớn chỉ vì Map cho phép lưu bất kỳ object nào.

**Không nên nhầm `ModelMap` với `Map` trả về JSON.** Nếu một handler HTML trả một `Map` hoặc `ModelMap` như return value, Spring MVC có thể hiểu đó là thuộc tính model rồi **tự suy ra view name**. Nếu handler REST dùng `@ResponseBody`, cùng loại `Map` lại có thể được serialize thành JSON. Annotation controller và cơ chế return value quyết định hành vi.

## 6. `ModelAndView`: đóng gói view và model

Khi muốn chỉ định cả view và dữ liệu ở cùng nơi:

~~~java
@GetMapping("/detail")
public ModelAndView detail() {
    return new ModelAndView("products/detail")
            .addObject("product", new ProductDto(101L, "Sách Spring MVC"))
            .addObject("pageTitle", "Chi tiết sản phẩm");
}
~~~

Đây là method minh họa trong `@Controller` và cần định nghĩa `ProductDto`. `ModelAndView` cho phép:

- Truyền tên view qua constructor `new ModelAndView("products/detail")` hoặc `setViewName(...)`.
- Thêm attribute bằng `addObject("key", value)` hoặc `addAllObjects(map)`.
- Đặt trực tiếp một `View` implementation qua constructor/`setView(View)`, thay vì logical name khi cần.
- Đặt HTTP status phù hợp bằng `setStatus(HttpStatus...)` trong Spring Framework 6.x (không biến thành `ResponseEntity`; status vẫn phục vụ response render view).

Một cách khác:

~~~java
ModelAndView mav = new ModelAndView();
mav.setViewName("products/detail");
mav.addObject("product", product);
mav.addObject("pageTitle", "Chi tiết sản phẩm");
return mav;
~~~

Những dòng trên cũng là minh họa đặt trong method trả `ModelAndView`. Nếu bỏ view name và không có điều kiện Spring coi request đã được xử lý hoàn toàn, framework có thể cần đến **view name mặc định**, tạo ra kết quả bất ngờ. Chọn tên view tường minh khi code cần dễ kiểm tra.

**Ví dụ status dành cho view:**

~~~java
ModelAndView mav = new ModelAndView("errors/not-found");
mav.setStatus(HttpStatus.NOT_FOUND);
mav.addObject("message", "Không tìm thấy sản phẩm");
return mav;
~~~

Cần có template lỗi tương ứng để render HTML. Thay đổi HTTP status thành 404 không tự động tạo template; Spring vẫn cần view resolver và tài nguyên thực tế. Với REST API trả JSON, thường dùng `ResponseEntity` hoặc `ProblemDetail` thay vì HTML `ModelAndView`.

## 7. Tên view logic được resolve như thế nào?

Giả sử controller:

~~~java
@GetMapping("/greeting")
public String greeting(Model model) {
    model.addAttribute("name", "Lan");
    return "hello";
}
~~~

Giả sử ứng dụng có `spring-boot-starter-thymeleaf`, Spring Boot thường tự cấu hình Thymeleaf view resolver. Mặc định:

~~~properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
~~~

Tên `"hello"` được ghép thành `classpath:/templates/hello.html`. Đặt file ở:

~~~text
src/main/resources/templates/hello.html
~~~

Một template tối thiểu:

~~~html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org" lang="vi">
<head><meta charset="UTF-8"><title>Demo</title></head>
<body>
  <h1 th:text="'Xin chào, ' + ${name}">Lời chào</h1>
</body>
</html>
~~~

Thymeleaf sẽ xử lý `th:text` bằng giá trị model `name` và escape dữ liệu theo ngữ cảnh HTML. Đây là điểm bảo mật quan trọng: dữ liệu từ client không nên được nhúng vào HTML raw bằng string concatenation thiếu escaping.

**Tên view logic không phải đường dẫn file trên máy.** Một view resolver có thể ghép prefix/suffix, một resolver khác có thể chọn JSP hoặc loại view khác. Không tự viết đường dẫn template dựa trực tiếp vào tham số của client (`return userSuppliedViewName;`) vì có thể dẫn đến hiển thị nhầm template hoặc rủi ro điều hướng.

### 7.1. Các hình thức tên view

| Handler trả về | Cách hiểu trong `@Controller` HTML |
| --- | --- |
| `"hello"` | Tên view logic, resolver tìm template |
| `"products/detail"` | Tên view logic nằm trong thư mục con |
| `"redirect:/products"` | Yêu cầu redirect HTTP tới URL `/products` |
| `"forward:/internal"` | Server-side forward đến đường dẫn khác |
| `new ModelAndView("hello")` | View `hello` và model kèm theo |
| `View` instance | Chỉ định view trực tiếp, không cần resolve tên |
| `Model`/`Map` return value | Model được cung cấp; view name thường suy ra từ request |

`redirect:` và `forward:` được nhận diện đặc biệt bởi những view resolver hỗ trợ chúng (như `UrlBasedViewResolver` và cơ chế cấu hình MVC thông dụng). Chúng **không phải tên template thông thường**.

### 7.2. Tên view mặc định (`RequestToViewNameTranslator`)

Nếu một HTML controller không trả view name nhưng cung cấp model và Spring chưa coi response đã xử lý hoàn toàn, framework có thể suy ra tên view dựa trên request URI thông qua `RequestToViewNameTranslator`, mặc định thường là `DefaultRequestToViewNameTranslator`.

Ví dụ request `GET /pages/implicit` có thể được diễn giải thành tên view `"pages/implicit"` dưới quy tắc mặc định. Khi đó Spring tìm template `templates/pages/implicit.html`.

Hành vi ngầm phụ thuộc cách đặt controller, route, translator và cấu hình resolver. Nếu muốn giảm sự phụ thuộc vào convention, **trả `String` view name tường minh**. Cũng cần tránh trả `void` từ controller HTML mà kỳ vọng luôn trả body rỗng: nó có thể kích hoạt **view name mặc định**.

### 7.3. Vì sao `@RestController` trả `"hello"` không tìm template?

~~~java
@Controller
class HtmlController {
    @GetMapping("/html")
    String html() {
        return "hello"; // Logical view name
    }
}

@RestController
class ApiController {
    @GetMapping("/api")
    String api() {
        return "hello"; // HTTP response body là chuỗi hello
    }
}
~~~

Đây là code minh họa gồm hai controller (cần import annotation). `@RestController` tương đương `@Controller` cùng `@ResponseBody` trên các method handler. Với `@ResponseBody`, Spring đưa String qua `HttpMessageConverter` thay vì đi qua view resolution. Muốn trả template HTML, chọn `@Controller` và return view name; muốn trả JSON hoặc text, chọn `@RestController` hoặc `@ResponseBody`.

## 8. Ví dụ Spring Boot 3.x có thể chạy: Model, ModelMap, ModelAndView và form

Tạo dự án bằng Spring Initializr:

- **Java:** 17 hoặc cao hơn.
- **Spring Boot:** nhánh 3.x.
- **Build:** Maven.
- **Dependencies:** Spring Web, Thymeleaf, Validation, Spring Boot Starter Test.

Các starter liên quan là `spring-boot-starter-web`, `spring-boot-starter-thymeleaf`, `spring-boot-starter-validation`, `spring-boot-starter-test`. Java package dùng `com.example.demo`. Nếu dùng Spring Boot 4.x/Framework 7.x, kiểm tra lại import và cấu hình dependency theo phiên bản.

Cấu trúc tệp:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/PageController.java
src/main/resources/templates/demo.html
src/main/resources/templates/pages/implicit.html
src/main/resources/templates/registration.html
src/main/resources/templates/thanks.html
src/test/java/com/example/demo/PageControllerTest.java
~~~

### 8.1. File khởi động

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 8.2. Controller đầy đủ

**`src/main/java/com/example/demo/PageController.java`**

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.ui.ModelMap;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.servlet.ModelAndView;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/pages")
public class PageController {

    @GetMapping("/model")
    public String useModel(Model model) {
        model.addAttribute("title", "Ví dụ Model");
        model.addAttribute("message", "Dữ liệu từ Model");
        return "demo";
    }

    @GetMapping("/modelmap")
    public String useModelMap(ModelMap model) {
        model.put("title", "Ví dụ ModelMap");
        model.addAttribute("message", "Dữ liệu từ ModelMap");
        return "demo";
    }

    @GetMapping("/modelandview")
    public ModelAndView useModelAndView() {
        ModelAndView mav = new ModelAndView("demo");
        mav.addObject("title", "Ví dụ ModelAndView");
        mav.addObject("message", "Dữ liệu từ ModelAndView");
        mav.setStatus(HttpStatus.OK);
        return mav;
    }

    // Không trả view name: MVC suy ra pages/implicit khi dùng
    // DefaultRequestToViewNameTranslator và request /pages/implicit.
    @GetMapping("/implicit")
    public Model implicitView(Model model) {
        model.addAttribute("title", "View ngầm định");
        model.addAttribute("message", "Dữ liệu từ view mặc định");
        return model;
    }

    @GetMapping("/register")
    public String showRegistration(Model model) {
        model.addAttribute("registration", new RegistrationForm());
        return "registration";
    }

    @PostMapping("/register")
    public String submitRegistration(
            @Valid @ModelAttribute("registration") RegistrationForm form,
            BindingResult errors,
            RedirectAttributes redirectAttributes) {

        if (errors.hasErrors()) {
            return "registration";
        }

        redirectAttributes.addFlashAttribute("name", form.getName());
        return "redirect:/pages/thanks";
    }

    @GetMapping("/thanks")
    public String thanks() {
        return "thanks";
    }

    public static class RegistrationForm {
        @NotBlank
        private String name;

        public RegistrationForm() {
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }
}
~~~

Điểm cần quan sát:

1. Ba handler đầu cùng dùng view logic **`"demo"`**; trong template, biến `title` và `message` là attribute model. Khác nhau chỉ là API xây kết quả.
2. `useModel` nhận `Model`, `useModelMap` nhận `ModelMap`; cả hai trả `String` view name.
3. `useModelAndView` trả một `ModelAndView` có `viewName`, model và status 200. `setStatus(OK)` ở đây để minh họa, thường có thể bỏ vì 200 là mặc định thành công.
4. `implicitView` trả `Model`; framework suy ra `pages/implicit` trong cấu hình dịch tên view mặc định. Đây là ví dụ về convention, **không phải cách nên ưu tiên trong API phức tạp**.
5. `showRegistration` đưa `RegistrationForm` vào model. Template Thymeleaf dùng nó để bind form HTML.
6. POST nhận form qua `@ModelAttribute`, áp dụng Bean Validation bằng `@Valid`, đặt `BindingResult` **ngay sau** tham số form để lấy lỗi binding/validation.
7. Nếu có lỗi, trả tên view `registration`, giữ model và `BindingResult` để template hiển thị lỗi. Nếu hợp lệ, dùng redirect theo mẫu **Post/Redirect/Get** và `RedirectAttributes` để chuyển flash attribute `name` qua request redirect tiếp theo.
8. `@Controller` là bắt buộc cho các handler trả template theo cách này. Nếu đổi thành `@RestController`, các `String` return value sẽ mang ngữ nghĩa HTTP body, gây khác biệt lớn.

### 8.3. Template chung cho cả ba cách

**`src/main/resources/templates/demo.html`**

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title th:text="${title}">Ví dụ Spring MVC</title>
</head>
<body>
  <h1 th:text="${title}">Tiêu đề mặc định</h1>
  <p id="message" th:text="${message}">Nội dung mặc định</p>
</body>
</html>
~~~

Khi controller trả `"demo"`, Thymeleaf đọc `demo.html` và thay nội dung `th:text` bằng attribute cùng tên trong model.

Ví dụ gọi `GET /pages/model`, HTML render chứa:

~~~html
<h1>Ví dụ Model</h1>
<p id="message">Dữ liệu từ Model</p>
~~~

Đây là phần nội dung minh họa được trích từ HTML, không phải toàn bộ response nguyên văn (response còn có `doctype`, `head` và các thẻ còn lại). Thymeleaf escape text để giảm nguy cơ nhúng HTML không mong muốn từ dữ liệu client.

### 8.4. Template dùng tên view được suy ra

**`src/main/resources/templates/pages/implicit.html`**

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title th:text="${title}">View ngầm định</title>
</head>
<body>
  <h1 th:text="${title}">Tiêu đề</h1>
  <p th:text="${message}">Nội dung</p>
</body>
</html>
~~~

Đường dẫn URL `/pages/implicit` thường dẫn đến logical view `pages/implicit` dưới translator mặc định. Nếu refactor route mà không đổi template hoặc ngược lại, bạn có thể gặp lỗi “template not found”. Đây là lý do các handler trả view name rõ ràng thường dễ bảo trì.

### 8.5. Template form và validation

**`src/main/resources/templates/registration.html`**

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Đăng ký</title>
</head>
<body>
  <h1>Đăng ký</h1>
  <form method="post" th:action="@{/pages/register}" th:object="${registration}">
    <label for="name">Tên</label>
    <input id="name" type="text" th:field="*{name}">
    <p th:if="${#fields.hasErrors('name')}"
       th:errors="*{name}">Lỗi của tên</p>
    <button type="submit">Gửi</button>
  </form>
</body>
</html>
~~~

- `th:object="${registration}"` gắn template vào form object trong model.
- `th:field="*{name}"` lấy hoặc đặt giá trị `name` theo object, hỗ trợ hiển thị lại form khi validation không đạt.
- Khi controller trả `"registration"` cùng `BindingResult`, Thymeleaf có thể hiển thị lỗi bằng `#fields.hasErrors` và `th:errors`.
- Dữ liệu từ form là input của người dùng: validation ở server vẫn cần thiết ngay cả khi HTML có thuộc tính `required`.
- Nếu dùng Spring Security và CSRF enabled, form phải mang CSRF token theo integration/config thực tế; đừng vô hiệu hóa CSRF chỉ để làm form hoạt động.

### 8.6. Template sau redirect

**`src/main/resources/templates/thanks.html`**

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Đăng ký thành công</title></head>
<body>
  <h1>Đăng ký thành công</h1>
  <p th:if="${name}" th:text="'Xin chào, ' + ${name}">Lời chào</p>
</body>
</html>
~~~

Sau POST hợp lệ, `redirect:/pages/thanks` trả HTTP redirect (thường 302 trong ví dụ), sau đó browser gửi GET tới `/pages/thanks`. `addFlashAttribute` giữ tên trong flash storage tạm thời cho lần request sau. Nó **không có nghĩa** mọi model attribute từ POST tự động xuất hiện trong GET tiếp theo.

Trong ứng dụng thật, POST nên lưu dữ liệu thông qua service trước khi redirect, và chỉ đưa thông tin cần thiết vào flash attributes. Flash được lưu tạm (thường liên quan session) và không phải nơi lưu dữ liệu nghiệp vụ lâu dài.

## 9. Gọi ứng dụng và xem view rendering

Chạy trong thư mục có `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows: `mvnw.cmd spring-boot:run`; nếu không có wrapper và đã cài Maven: `mvn spring-boot:run`.

Các URL:

~~~text
GET http://localhost:8080/pages/model
GET http://localhost:8080/pages/modelmap
GET http://localhost:8080/pages/modelandview
GET http://localhost:8080/pages/implicit
GET http://localhost:8080/pages/register
GET http://localhost:8080/pages/thanks
~~~

Ba URL đầu phải render **cùng file `demo.html`** nhưng chữ hiển thị khác nhau:

| URL | `title` | `message` |
| --- | --- | --- |
| `/pages/model` | `Ví dụ Model` | `Dữ liệu từ Model` |
| `/pages/modelmap` | `Ví dụ ModelMap` | `Dữ liệu từ ModelMap` |
| `/pages/modelandview` | `Ví dụ ModelAndView` | `Dữ liệu từ ModelAndView` |

Bạn có thể dùng `curl -i` để xem status, response headers và HTML output:

~~~bash
curl -i http://localhost:8080/pages/model
curl -i http://localhost:8080/pages/modelmap
curl -i http://localhost:8080/pages/modelandview
~~~

Kết quả là HTML (thường `Content-Type: text/html`), **không phải JSON**. Với Thymeleaf, toàn bộ `model` được dùng khi template đánh giá các expression `${...}`.

Thử form hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/pages/register   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode "name=Lan"
~~~

Đáp ứng kỳ vọng là **redirect** (thường 302) với header `Location: /pages/thanks` trong cấu hình chuẩn. `curl` không giữ và gửi session cookie qua các lệnh tách biệt nếu không yêu cầu; để quan sát flash attribute sau redirect, dùng browser hoặc `curl -L -c cookies.txt -b cookies.txt` với cookie jar và đúng điều kiện theo redirect. Đối với flash attribute liên quan session, không giả định `curl -L` đơn lẻ luôn nhìn thấy lời chào.

Để thử lỗi validation, gửi `name` rỗng:

~~~bash
curl -i -X POST http://localhost:8080/pages/register   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode "name="
~~~

Controller trả **view `registration`** (thường 200 HTTP trong ví dụ) và template hiển thị lỗi tại trường `name`, không redirect. Nếu sản phẩm cần status 400 cho validation khi render form, phải chủ động đặt status thích hợp; `BindingResult` không tự áp đặt 400 khi handler quyết định render lại một HTML form.

## 10. Kiểm thử `Model`, `ModelMap`, `ModelAndView` bằng MockMvc

Có `spring-boot-starter-test` trong dự án, tạo **`src/test/java/com/example/demo/PageControllerTest.java`**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@WebMvcTest(PageController.class)
class PageControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void modelAddsDataAndReturnsViewName() throws Exception {
        mockMvc.perform(get("/pages/model"))
                .andExpect(status().isOk())
                .andExpect(view().name("demo"))
                .andExpect(model().attribute("title", "Ví dụ Model"))
                .andExpect(model().attribute(
                        "message", "Dữ liệu từ Model"));
    }

    @Test
    void modelMapAddsDataAndReturnsSameView() throws Exception {
        mockMvc.perform(get("/pages/modelmap"))
                .andExpect(status().isOk())
                .andExpect(view().name("demo"))
                .andExpect(model().attribute("title", "Ví dụ ModelMap"))
                .andExpect(model().attribute(
                        "message", "Dữ liệu từ ModelMap"));
    }

    @Test
    void modelAndViewCombinesDataAndView() throws Exception {
        mockMvc.perform(get("/pages/modelandview"))
                .andExpect(status().isOk())
                .andExpect(view().name("demo"))
                .andExpect(model().attribute(
                        "message", "Dữ liệu từ ModelAndView"));
    }

    @Test
    void implicitViewNameUsesDefaultTranslator() throws Exception {
        mockMvc.perform(get("/pages/implicit"))
                .andExpect(status().isOk())
                .andExpect(view().name("pages/implicit"))
                .andExpect(model().attribute(
                        "message", "Dữ liệu từ view mặc định"));
    }

    @Test
    void formPageProvidesModelAttribute() throws Exception {
        mockMvc.perform(get("/pages/register"))
                .andExpect(status().isOk())
                .andExpect(view().name("registration"))
                .andExpect(model().attributeExists("registration"));
    }

    @Test
    void validFormUsesRedirectAndFlash() throws Exception {
        mockMvc.perform(post("/pages/register")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", "Lan"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/pages/thanks"))
                .andExpect(flash().attribute("name", "Lan"));
    }

    @Test
    void invalidFormReturnsToViewWithFieldErrors() throws Exception {
        mockMvc.perform(post("/pages/register")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("name", ""))
                .andExpect(status().isOk())
                .andExpect(view().name("registration"))
                .andExpect(model().attributeHasFieldErrors(
                        "registration", "name"));
    }
}
~~~

Chạy test:

~~~bash
./mvnw test
~~~

Các test khẳng định chính xác sự phân tách giữa **tên view** và **attribute model**. `view().name("demo")` xác minh việc chọn tên logic; `model().attribute(...)` kiểm tra dữ liệu được đưa đến view. Kết quả view resolver có thể còn phụ thuộc engine và cấu hình test slice, nên giữ đúng dependency Thymeleaf và template khi chạy.

Nếu muốn kiểm tra HTML đã render, có thể thêm test với `content().string(containsString("Dữ liệu từ Model"))` và import matcher Hamcrest; điều này đòi view đã thực sự được render. Ứng dụng HTML production cần cả test controller và test integration của template để phát hiện template sai đường dẫn/cú pháp.

## 11. `@ModelAttribute` bổ sung model trước khi render

Ngoài việc gọi `model.addAttribute(...)` trong handler, Spring MVC hỗ trợ method có annotation `@ModelAttribute` để tạo dữ liệu dùng chung:

~~~java
@Controller
@RequestMapping("/shop")
public class ShopController {

    @ModelAttribute("siteName")
    public String siteName() {
        return "Cửa hàng Spring";
    }

    @GetMapping("/home")
    public String home(Model model) {
        model.addAttribute("pageTitle", "Trang chủ");
        return "shop/home";
    }
}
~~~

Đây là class minh họa, cần import. Phương thức `siteName()` không phải endpoint HTTP; nó tạo attribute `siteName` trong model trước khi các handler phù hợp được gọi. Template `shop/home` có thể dùng cả `${siteName}` và `${pageTitle}`. Có thể đưa `@ModelAttribute` method vào `@ControllerAdvice` nếu thật sự cần dữ liệu chung cho nhiều controller.

**Tránh đặt dữ liệu thay đổi nhanh hoặc truy vấn database nặng vào một advice áp dụng mọi route** nếu không cần thiết; method chung có thể bị gọi ở nhiều request. Đừng dùng `@ModelAttribute` để vô tình đưa thông tin nhạy cảm vào view HTML.

`@ModelAttribute` trên **tham số handler** lại có nhiệm vụ truy cập/tạo target object và bind giá trị request; không hoàn toàn tương đương `@ModelAttribute` ở mức method chuẩn bị model.

## 12. View name, redirect, forward và vòng đời dữ liệu model

### `return "redirect:/..."`

Dùng khi browser cần **request mới**. Sau POST thành công, redirect giúp tránh trình duyệt gửi lại form khi refresh. Giá trị model thông thường không nên được hiểu là sẽ tồn tại tự động trong request mới. `RedirectAttributes` có hai cơ chế:

- `addAttribute(...)`: thường dùng cho URL template variables hoặc query parameters khi redirect. Tránh đưa mật khẩu/token/thông tin nhạy cảm vào URL.
- `addFlashAttribute(...)`: lưu tạm dữ liệu cho request sau khi redirect (thường trong session flash map), thích hợp cho thông điệp xác nhận hoặc một phần trạng thái hiển thị.

**Ví dụ minh họa độc lập với controller phần 8:**

~~~java
@PostMapping("/save")
public String save(RedirectAttributes attributes) {
    long id = 101L; // Giả sử service đã tạo tài nguyên.
    attributes.addAttribute("id", id);
    attributes.addFlashAttribute("notice", "Đã lưu");
    return "redirect:/products/{id}";
}
~~~

Khi browser đến `/products/101`, giá trị flash `notice` có thể được đưa vào model ở request đích. Không lưu object dung lượng lớn hoặc dữ liệu nhạy cảm vào flash storage.

### `return "forward:/..."`

Server **forward nội bộ** request hiện tại đến path khác bằng servlet request dispatcher, thường không đổi URL trên thanh địa chỉ và không yêu cầu browser tự gửi redirect request. Request attributes có thể được tiếp tục dùng trong quá trình forward. Hãy tránh vòng forward vô hạn và chỉ forward tới route/view thực sự tồn tại.

### Đường dẫn tuyệt đối và tên view logic

`"products/detail"` là tên view, không tự động là đường dẫn HTTP `/products/detail`. Ngược lại, `"redirect:/products/detail"` chỉ đích của HTTP redirect. Một template dưới `templates/products/detail.html` không bắt buộc có endpoint `/products/detail` cùng tên; controller nào trả logical view đó cũng có thể render template.

## 13. Model trong form validation: khi nào dữ liệu lỗi còn ở lại?

Với `@Valid @ModelAttribute("registration") RegistrationForm form, BindingResult errors`, Spring tạo hoặc lấy form object, bind input, chạy validation và đặt thông tin lỗi vào model cùng object. Khi method trả `"registration"`, view có thể đọc giá trị đã nhập và lỗi theo tên field. Đó là lý do biểu mẫu có thể hiển thị lại trường nhập sau lỗi.

- `BindingResult` phải đặt **ngay sau** tham số được validate để handler nhận lỗi của target đó; nếu không, Spring có thể ném exception hoặc không ghép lỗi theo ý muốn.
- `model.addAttribute("registration", ...) ` khi render GET cung cấp form object ban đầu. Khi POST invalid, Spring thường đã có object đó từ binding; không nên tạo mới và ghi đè nó trước khi render lại, nếu cần giữ giá trị user nhập và lỗi.
- Nếu đang dùng Thymeleaf, `th:object`, `th:field` và `th:errors` giúp kết nối HTML form với model và `BindingResult`.
- Validation đối với DTO chỉ xác minh dữ liệu; lưu thành công phải qua service/repository thật và kiểm tra quyền theo ngữ cảnh ứng dụng.

Một model có thể chứa nhiều form attribute. Tránh dùng những tên attribute quá chung như `"data"` cho nhiều form trên cùng trang, vì template và error binding khó phân biệt.

## 14. Khi nào nên trả `ModelAndView` thay vì `String`?

Hai phong cách thường tương đương về output:

~~~java
@GetMapping("/simple")
public String simple(Model model) {
    model.addAttribute("message", "Xin chào");
    return "hello";
}
~~~

~~~java
@GetMapping("/combined")
public ModelAndView combined() {
    return new ModelAndView("hello")
            .addObject("message", "Xin chào");
}
~~~

Đây là hai method minh họa trong controller cùng có template `hello.html`. Chúng có thể tạo HTML giống nhau; không có quy tắc hiệu năng tổng quát nói `ModelAndView` luôn nhanh hơn hay chậm hơn `Model`.

**Nên dùng `Model` + `String`** khi method ngắn, đọc tự nhiên: “thêm attribute vào model, trả tên view”. **Nên dùng `ModelAndView`** khi cần tập hợp view/model/status trong một return object, khi xử lý exception theo hướng HTML hoặc khi framework extension phù hợp với kiểu `ModelAndView`.

Trả `ModelAndView` không bắt buộc phải khai báo tham số `Model`; tuy vậy bạn vẫn có thể có implicit model từ các cơ chế khác. Đừng thêm dữ liệu hai lần qua cả model argument và ModelAndView trừ khi có mục đích rõ.

## 15. Những lỗi phổ biến và cách chẩn đoán

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Browser hiển thị đúng chữ `demo` thay vì HTML | Dùng `@RestController` hoặc `@ResponseBody` | Đổi thành `@Controller` cho handler cần view |
| `TemplateInputException` hoặc view không tìm được | Logical view không khớp vị trí template/prefix/suffix | Kiểm tra `templates/demo.html`, tên view và Thymeleaf dependency |
| Template render nhưng attribute rỗng | Sai key giữa `addAttribute` và `${...}` | So lại tên property, null và logic controller |
| Gọi `model.put(...)` nhưng biến là `Model` | `Model` là interface không có `put` | Dùng `addAttribute` hoặc đổi sang `ModelMap` |
| Template có vòng forward/redirect | Logic định tuyến không hợp lý hoặc tên view trùng route | Kiểm tra return value, view resolver và mapping |
| Sau POST/redirect mất thông báo | Model thường không sống qua HTTP request mới | Sử dụng `RedirectAttributes.addFlashAttribute` |
| Form invalid mất dữ liệu cũ | Ghi đè form object hoặc không render đúng binding | Giữ `@ModelAttribute` + `BindingResult` và Thymeleaf `th:field` |
| `void` ở HTML controller dẫn tới view ngoài ý muốn | Spring áp dụng default view name | Return tên view tường minh hoặc xử lý response rõ |
| Trả `Map` nhưng muốn JSON | Không có `@ResponseBody` hoặc controller kiểu REST | Dùng `@RestController` hoặc `ResponseEntity` |
| User input trở thành tên template | Tạo view name bằng dữ liệu client không kiểm soát | Whitelist view name và tách input khỏi cơ chế định tuyến |
| Test view name PASS nhưng trang chạy lỗi | MockMvc chưa kiểm tra render template thực | Thêm integration test kiểm tra HTML và tài nguyên |
| HTML đúng nhưng URL sau POST vẫn là endpoint POST | Handler render trực tiếp thay vì redirect | Dùng Post/Redirect/Get nếu quy trình yêu cầu |

### Lỗi `Model` không phải response JSON

~~~java
@GetMapping("/wrong")
public Model wrong(Model model) {
    model.addAttribute("message", "Hello");
    return model;
}
~~~

Đây là **minh họa trong HTML `@Controller`**: Spring có thể coi return value là model và suy ra tên view từ URL. Không dùng mẫu này để trả REST JSON. Với REST endpoint, nên trả DTO/record từ `@RestController` hoặc `ResponseEntity<Dto>`.

### Lỗi view name dùng trực tiếp client input

~~~java
@GetMapping("/show")
public String show(@RequestParam String template) {
    return template;
}
~~~

Đây là **mẫu phản diện**, không nên dùng. Client có thể tác động vào việc chọn template/redirect/forward. Nên map đầu vào tới một tập **view name cố định được cho phép** ở phía server, ví dụ enum hoặc `switch` với default an toàn.

## 16. Câu hỏi ôn tập

**1. `Model` và `ModelMap` khác nhau thế nào?**

`Model` là interface API của model; `ModelMap` là class dựa trên Map, có `put`, `get`, `addAttribute`. Cả hai đều dùng để chứa attribute mà view đọc được trong request.

**2. Tên view logic `"orders/list"` có nghĩa Spring truy cập URL `/orders/list` không?**

Không. Nó là tên view để resolver tìm tài nguyên render, ví dụ `templates/orders/list.html`. Chỉ các prefix như `redirect:` mới diễn đạt việc browser điều hướng sang URL khác.

**3. Khi nào chọn `ModelAndView`?**

Khi muốn trả kết quả gói view + model và đôi khi status trong một object. Nếu chỉ cần thêm attribute và trả tên view, `Model` + `String` thường ngắn gọn.

**4. Vì sao `@RestController` trả `"hello"` không render `hello.html`?**

Vì `@RestController` bao gồm ngữ nghĩa `@ResponseBody`, nên String được ghi thành HTTP response body thông qua converter, không phải logical view name.

**5. View name ngầm định dùng khi nào?**

Khi handler HTML không chỉ rõ tên view và response chưa được xem là xử lý hoàn toàn. Spring có thể dựa trên request path qua `RequestToViewNameTranslator` để suy ra tên view.

**6. Model của POST có tự giữ cho GET sau redirect không?**

Không. Đây là request khác. Khi cần chuyển thông điệp ngắn qua redirect, dùng `RedirectAttributes.addFlashAttribute` và hiểu vòng đời flash.

## 17. Checklist thực hành

1. Với trang HTML, dùng `@Controller`, return logical view name tường minh và truyền attribute qua `Model` hoặc `ModelMap`.
2. Với logic cần gom view + model + status, dùng `ModelAndView` và khai báo view name rõ.
3. Xác nhận ViewResolver đúng loại template, đường dẫn, prefix/suffix và tên file có phân biệt hoa/thường trên hệ điều hành tương ứng.
4. Test cả tên view, attribute model và HTML render. Với form, test GET tạo form, POST hợp lệ redirect, POST không hợp lệ trả view với field errors.
5. Kiểm soát nguồn dữ liệu đưa vào template, dùng escaping của engine và tránh xây tên view từ input client.
6. Phân biệt `redirect:`, `forward:`, implicit view, `@ResponseBody` và `@RestController`.
7. Giữ model dành cho dữ liệu hiển thị, không nhầm với repository/entity hoặc cơ chế lưu dài hạn.

## Tài liệu chính thức

- [Spring Framework 6.2 — Controller Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/return-types.html)
- [Spring Framework 6.2 — Controller Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework 6.2 — `@ModelAttribute` methods](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-modelattrib-methods.html)
- [Spring Framework 6.2 — Redirect Attributes](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html)
- [Spring Framework — View Resolvers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/viewresolver.html)
- [Spring Boot — Template Engines and MVC Views](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)

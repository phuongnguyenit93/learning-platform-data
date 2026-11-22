# @ResponseBody và khác biệt với tên view trả về từ @Controller

## 1. Mục tiêu: cùng một String, hai cách hiểu hoàn toàn khác nhau

Giả sử controller có hai method đều trả về `"hello"`. Trong Spring MVC (Servlet stack), ý nghĩa HTTP khác nhau tùy cơ chế xử lý giá trị trả về:

~~~java
@Controller
class PageController {
    @GetMapping("/page")
    public String page() {
        return "hello";
    }
}
~~~

Ở đây `"hello"` là **tên view**. Spring chọn một `ViewResolver` thích hợp, tìm template/view tương ứng và **render kết quả** vào HTTP response. Nếu không tìm được view, request có thể thất bại tùy cấu hình view technology. Giá trị return **không tự được gửi nguyên văn** dưới dạng response body.

~~~java
@Controller
class TextController {
    @GetMapping("/text")
    @ResponseBody
    public String text() {
        return "hello";
    }
}
~~~

Ở đây `"hello"` là **nội dung response body**, không qua cơ chế tìm view. `StringHttpMessageConverter` thường viết nó thành text theo media type được chọn.

Và khi đặt `@RestController` lên lớp, ý nghĩa của `@ResponseBody` được áp dụng mặc định cho các handler:

~~~java
@RestController
class ApiController {
    @GetMapping("/api/hello")
    public String hello() {
        return "hello";
    }
}
~~~

Cả ba fragment chỉ minh họa annotation và ý nghĩa return value; phần **ví dụ ứng dụng hoàn chỉnh** bên dưới có đầy đủ file/import/test.

**Bài học cần đạt:**
1. Phân biệt `@Controller`, `@ResponseBody` và `@RestController`.
2. Hiểu Spring MVC quyết định khi nào dùng `ViewResolver` và khi nào dùng `HttpMessageConverter`.
3. Biết `String`, DTO, `ResponseEntity`, `ModelAndView`, `redirect:` được xử lý thế nào.
4. Viết controller và MockMvc test xác nhận body, media type, model/view, redirect.
5. Chẩn đoán các lỗi trả nhầm tên view, render nhầm text, sai Content-Type hoặc bị HTTP 406.

Ví dụ hướng đến Java 17+ và Spring Boot 3.x / Spring Framework 6.x; các nguyên tắc cốt lõi vẫn có giá trị ở Spring MVC hiện đại. Không lấy ví dụ WebFlux để suy ra chính xác tên implementation ở Servlet stack.

## 2. Hai nhánh xử lý phản hồi trong Spring MVC

### 2.1. Khởi đầu giống nhau, kết thúc khác nhau

Khi nhận HTTP request, Spring MVC:
1. `DispatcherServlet` phối hợp `HandlerMapping` xác định handler.
2. `HandlerAdapter` phân giải tham số và gọi controller method.
3. Một `HandlerMethodReturnValueHandler` phù hợp với **kiểu giá trị trả về và metadata annotation** xử lý kết quả.
4. Nếu là model/view, Spring resolve và render view; nếu là body, converter serialize/write dữ liệu.

~~~text
HTTP GET /...
     │
     ▼
DispatcherServlet → HandlerMapping → Controller method
                                         │
                          return "hello" │
                                         ▼
                        HandlerMethodReturnValueHandler
                                  │                │
                     @Controller, String       @ResponseBody
                     (view name)               hoặc @RestController
                                  │                │
                                  ▼                ▼
                            ViewResolver      HttpMessageConverter
                                  │                │
                                  ▼                ▼
                            View.render()     write HTTP response body
                                  │                │
                                  └────────┬───────┘
                                           ▼
                                     HTTP response
~~~

Đây là sơ đồ giản lược để hiểu hai nhánh. Trong runtime, các resolver/handler cụ thể, filter, interceptor, exception handler và view technology ảnh hưởng kết quả; Spring **không tự đoán “String có vẻ là HTML” để chọn view**.

### 2.2. `@Controller` nói gì?

`@Controller` là stereotype đánh dấu thành phần MVC được component scan phát hiện; nó **không tuyên bố rằng mọi return value là JSON**.

Ví dụ:

~~~java
@Controller
class ShopPageController {
    @GetMapping("/products")
    public String products(Model model) {
        model.addAttribute("title", "Products");
        return "products";
    }
}
~~~

`"products"` được xem là tên view, `Model` chứa dữ liệu đưa vào quá trình render. Với Thymeleaf và cấu hình chuẩn, template có thể nằm ở `classpath:/templates/products.html`; với JSP hoặc view resolver khác, đường dẫn/tên file có thể thay đổi.

Không phải mọi method trong `@Controller` đều bắt buộc trả view: nếu trả `ResponseEntity<?>`, gắn `@ResponseBody`, hoặc tự ghi `HttpServletResponse`, Spring có thể xử lý response trực tiếp.

### 2.3. `@ResponseBody` thay đổi điều gì?

`@ResponseBody` bảo Spring xử lý **return value của method như dữ liệu gửi vào response body**, thông qua `HttpMessageConverter`. Có thể đặt annotation lên:
- **Một method** trong `@Controller`, giúp controller có cả trang HTML và endpoint API.
- **Lớp `@Controller`**, tác động lên các handler method tương ứng.

Annotation này **không có nghĩa chắc chắn là JSON**. Dạng biểu diễn phụ thuộc **kiểu Java**, các converter được cấu hình, điều kiện `produces`, header `Accept` và negotiation. `String` thường là `text/plain`, DTO thường là JSON nếu Jackson converter có sẵn và content negotiation phù hợp, `byte[]` có converter khác.

`@ResponseBody` cũng không tự tạo đối tượng response. Giá trị `null`/`void` có xử lý riêng theo signature và có thể kết thúc với body rỗng; không dùng `return null` để biểu thị một status code cụ thể.

### 2.4. `@RestController` thực chất là gì?

`@RestController` là annotation tổng hợp mang ý nghĩa của **`@Controller` + `@ResponseBody` ở cấp lớp**. Nó phù hợp khi handler chủ yếu là REST API, vì không phải lặp `@ResponseBody` trên từng method:

~~~java
@RestController
@RequestMapping("/api")
class ProductApi {
    @GetMapping("/health")
    public String health() {
        return "ok";
    }
}
~~~

Response body là `ok`; `"ok"` không phải tên template. Vì thế **không nên đưa các method trả tên view vào một `@RestController`** rồi mong Spring tự chuyển sang HTML. Nếu muốn trang HTML, dùng `@Controller` phù hợp hoặc trả hẳn nội dung HTML với media type tương ứng (một cách thiết kế khác).

## 3. Bảng so sánh các kiểu return phổ biến

| Controller và return value | Cách Spring MVC diễn giải | Phần trả cho client |
| --- | --- | --- |
| `@Controller` + `String "home"` | Tên view `home` | HTML hoặc kết quả do view render |
| `@Controller` + `String "redirect:/login"` | Tên view đặc biệt để redirect | HTTP redirect, thường 302 |
| `@Controller` + `String "forward:/internal"` | Tên view đặc biệt để forward | Servlet forward theo cấu hình |
| `@Controller` + `@ResponseBody String "home"` | Nội dung body | Chuỗi `home`, không tìm template |
| `@Controller` + `@ResponseBody ProductDto` | Body qua converter | Thường JSON nếu có Jackson |
| `@RestController` + `String "redirect:/login"` | Chuỗi body | Literal `redirect:/login`, không phải redirect |
| `@RestController` + `ProductDto` | Body qua converter | Thường JSON |
| `@Controller` + `ResponseEntity<ProductDto>` | Phản hồi HTTP đầy đủ, không cần `@ResponseBody` | Status, headers và body được chuyển đổi |
| `@Controller` + `ModelAndView` | View + model (và tùy chọn status) | Render view |
| `@Controller` + `Model` hoặc `Map` | Cập nhật model, tìm tên view ngầm nếu cần | Render view sau khi resolve |

Bảng áp dụng trường hợp handler bình thường, chưa xét custom return handlers. Điểm hay bị bỏ qua: `ResponseEntity<T>` là **return type đặc biệt**; ngay cả khi class chỉ có `@Controller`, nó vẫn có thể ghi response body mà không cần `@ResponseBody`.

### 3.1. Tại sao `String` đặc biệt?

Spring MVC có handler giải thích một `String`/`CharSequence` là tên logical view khi không có `@ResponseBody` và không được return handler khác xử lý trước. `@ResponseBody` làm route qua handler viết body: `StringHttpMessageConverter` ghi ký tự. Vậy **cùng kiểu Java `String` không đủ để suy luận hành vi HTTP**.

Ví dụ dễ sai:

~~~java
@Controller
class MistakeController {
    @GetMapping("/api/status")
    public String status() {
        return "READY";
    }
}
~~~

Dù developer muốn trả `READY` cho API, Spring sẽ đi tìm **view `READY`**. Nếu không có template/view tương ứng, client có thể nhận lỗi server hoặc cơ chế fallback riêng của ứng dụng, thay vì text `READY`. Cách sửa là thêm `@ResponseBody` hoặc dùng `@RestController` nếu toàn bộ class là API.

### 3.2. `ResponseEntity` kiểm soát nhiều hơn body

~~~java
@GetMapping("/api/orders/{id}")
public ResponseEntity<OrderDto> get(@PathVariable long id) {
    OrderDto order = lookup(id);
    if (order == null) {
        return ResponseEntity.notFound().build();
    }
    return ResponseEntity.ok(order);
}
~~~

Đây là **fragment** vì `OrderDto` và `lookup` phụ thuộc ứng dụng. Trả `ResponseEntity.ok(order)` thiết lập status 200; `notFound().build()` trả 404 không body. Không cần thêm `@ResponseBody` để Spring xử lý `ResponseEntity`. Dùng `ResponseEntity.created(uri).body(dto)` khi muốn 201 kèm header `Location`.

`@ResponseStatus` có thể chỉ định status cho một handler, nhưng không hỗ trợ linh hoạt theo từng nhánh logic như `ResponseEntity`. Đừng đồng nhất **có body** với **HTTP 200**: vẫn có thể trả 201/204/404 tùy kiểu xử lý, và với 204 thì body phải được bỏ.

## 4. `HttpMessageConverter`: tại sao object lại thành JSON?

Khi Spring chọn nhánh response body, `RequestResponseBodyMethodProcessor` hoặc return handler tương ứng phối hợp với `HttpMessageConverter` để **serialize** value.

Ví dụ mapping:

~~~java
@GetMapping(path = "/api/products/7", produces = "application/json")
@ResponseBody
public ProductDto product() {
    return new ProductDto(7L, "Spring MVC");
}
~~~

`ProductDto` trong fragment là record/POJO được định nghĩa ở ứng dụng. Với `spring-boot-starter-web` và Jackson mặc định, body thường là:

~~~json
{"id":7,"name":"Spring MVC"}
~~~

Với cùng nội dung nếu viết:

~~~java
@GetMapping(path = "/api/products/title", produces = "text/plain")
@ResponseBody
public String title() {
    return "Spring MVC";
}
~~~

Body là:

~~~text
Spring MVC
~~~

**Không có cú pháp dấu ngoặc kép JSON trong response text trên**. Chuỗi `String` không tự được JSON encode chỉ vì method đặt trong `@RestController`. Cần phân biệt:
- `StringHttpMessageConverter`: thường xử lý `String` thành text.
- Jackson JSON converter, trong Spring Framework 6.x thường là `MappingJackson2HttpMessageConverter`: có thể serialize record/POJO sang JSON.
- `ByteArrayHttpMessageConverter`, `ResourceHttpMessageConverter` và converter khác: đáp ứng các kiểu body tương ứng.
- Converter có thể được tùy chỉnh; kết quả thực tế phụ thuộc HTTP negotiation và application configuration.

### 4.1. `Content-Type`, `Accept`, `produces`

- `Content-Type` trong **response** mô tả định dạng dữ liệu server gửi.
- `Accept` trong **request** nói client có thể nhận những định dạng nào.
- `@GetMapping(produces = "...")` ràng buộc representation của handler và tham gia chọn mapping/negotiation.
- `@PostMapping(consumes = "...")` ràng buộc Content-Type của **request body**, không quyết định response luôn là JSON.

Nếu client gửi `Accept: application/xml` mà endpoint chỉ có mapping sản xuất `application/json`, Spring có thể trả **406 Not Acceptable**. Nếu client gửi JSON request body cho method chỉ `consumes=text/plain`, có thể gặp **415 Unsupported Media Type**. Không có nghĩa mọi method trả DTO đều luôn JSON: cần converter và media type tương thích.

**Lỗi nguy hiểm:** ép `produces="application/json"` lên method trả `String` nhưng chỉ trả literal `hello` mà không có dấu ngoặc kép JSON. Vì converter cho `String` có thể ghi chuỗi thô với media type JSON, client có thể nhận payload **không phải JSON hợp lệ**. Nếu muốn trả JSON string, hãy kiểm soát serialization thật rõ; với API thông thường, nên trả **DTO/record** thay vì cố dùng `String` như body JSON.

### 4.2. Nội dung object trả về chưa chắc đúng như Java debugger

Object Java có thể chứa `LocalDate`, enum, nested record, object references, Jackson annotations và lazy JPA proxies. Cấu hình serialization quyết định tên field, định dạng date, null handling và lỗi vòng tham chiếu. **Không trả thẳng entity nhạy cảm** rồi giả định JSON chỉ chứa field mong muốn; định nghĩa DTO response ổn định.

## 5. Ví dụ hoàn chỉnh: HTML view, text body và JSON body trong cùng ứng dụng

Ví dụ Java 17 + Spring Boot 3.x sử dụng **Thymeleaf** để chứng minh view name hoạt động và Spring MVC/Jackson để trả dữ liệu API. Đây là **một ứng dụng duy nhất** có ba loại endpoint để có thể so sánh trực tiếp.

Cấu trúc project:

~~~text
response-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/responsedemo/
    │   │   ├── ResponseDemoApplication.java
    │   │   └── web/
    │   │       ├── GreetingPageController.java
    │   │       ├── GreetingApiController.java
    │   │       └── GreetingDto.java
    │   └── resources/templates/
    │       └── greeting.html
    └── test/java/com/example/responsedemo/web/
        └── GreetingControllerTest.java
~~~

### 5.1. Gradle dependencies

`settings.gradle`:

~~~groovy
rootProject.name = 'response-demo'
~~~

`build.gradle` (minh họa project Spring Boot 3.3.5, Java 17; có thể dùng version 3.x được dự án đang quản lý):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` cung cấp Spring MVC và JSON converter thông thường; `spring-boot-starter-thymeleaf` cung cấp view technology, view resolver và template rendering. Nếu bỏ Thymeleaf mà không cung cấp một view resolver khác, return `"greeting"` **không đủ** để render HTML.

Ví dụ chạy bằng Gradle wrapper có sẵn trong project:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell/CMD có thể dùng `.\gradlew.bat bootRun`. Các lệnh trên giả định wrapper và network dependency cần thiết đã sẵn sàng; không phải lệnh `javac` cho code phụ thuộc Spring, vì Gradle giải quyết classpath.

### 5.2. Spring Boot entry point

`src/main/java/com/example/responsedemo/ResponseDemoApplication.java`:

~~~java
package com.example.responsedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResponseDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResponseDemoApplication.class, args);
    }
}
~~~

Nằm ở package cha để component scan thấy controllers tại `web`.

### 5.3. `@Controller` trả tên view

`src/main/java/com/example/responsedemo/web/GreetingPageController.java`:

~~~java
package com.example.responsedemo.web;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class GreetingPageController {

    @GetMapping("/pages/greeting")
    public String greeting(
            @RequestParam(name = "name", defaultValue = "Guest") String name,
            Model model) {

        model.addAttribute("name", name);
        return "greeting";
    }

    @GetMapping("/pages/home")
    public String home() {
        return "redirect:/pages/greeting?name=Guest";
    }
}
~~~

- Trả `"greeting"` để Spring tìm view/template; không gửi literal `greeting`.
- `Model` đưa `name` vào quá trình render.
- `"redirect:/..."` là tiền tố đặc biệt được các view resolver phù hợp dùng để phát HTTP redirect. Nó không được in làm nội dung trang.
- Code HTML render là kết quả **template + model**, khác Java return value.

### 5.4. Thymeleaf template cho view

`src/main/resources/templates/greeting.html`:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Greeting page</title>
</head>
<body>
    <h1 th:text="'Hello ' + ${name}">Hello Guest</h1>
    <p>This page is rendered from a Thymeleaf template.</p>
</body>
</html>
~~~

Với `GET /pages/greeting?name=Lan`, Thymeleaf sẽ render phần heading thành:

~~~html
<h1>Hello Lan</h1>
~~~

`th:text` xử lý escaped text khi chèn dữ liệu, tránh coi tên người dùng như HTML tùy ý. Tránh dùng các cách đưa dữ liệu chưa tin cậy vào template dưới dạng unescaped HTML trừ khi đã có policy làm sạch thích hợp.

### 5.5. DTO cho REST response

`src/main/java/com/example/responsedemo/web/GreetingDto.java`:

~~~java
package com.example.responsedemo.web;

public record GreetingDto(long id, String greeting) {
}
~~~

Record bất biến giúp định nghĩa shape JSON rõ ràng trong demo.

### 5.6. `@RestController` trả JSON/text và dùng `ResponseEntity`

`src/main/java/com/example/responsedemo/web/GreetingApiController.java`:

~~~java
package com.example.responsedemo.web;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class GreetingApiController {

    @GetMapping(path = "/greeting", produces = MediaType.APPLICATION_JSON_VALUE)
    public GreetingDto greeting() {
        return new GreetingDto(7L, "Hello Lan");
    }

    @GetMapping(path = "/message", produces = MediaType.TEXT_PLAIN_VALUE)
    public String message() {
        return "Hello Lan";
    }

    @GetMapping(path = "/response", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<GreetingDto> response() {
        return ResponseEntity.ok(new GreetingDto(8L, "Hello from ResponseEntity"));
    }

    @GetMapping(path = "/redirect-text", produces = MediaType.TEXT_PLAIN_VALUE)
    public String redirectText() {
        return "redirect:/pages/greeting";
    }
}
~~~

Quan sát:
- `GET /api/greeting` dùng Jackson viết JSON record.
- `GET /api/message` viết chính chuỗi `Hello Lan` vào body, không tìm template.
- `GET /api/response` trả status 200 và body JSON theo `ResponseEntity`.
- `GET /api/redirect-text` trả chuỗi literal `redirect:/pages/greeting`, **không** phát 302. `@RestController` đã bật body semantics ở cấp lớp.

### 5.7. Ví dụ `@Controller` chỉ bật body ở một method

Để kết hợp một controller phục vụ HTML và text, có thể thêm method sau **vào `GreetingPageController`**, cùng với các imports cần thiết:

~~~java
// Fragment đưa vào @Controller đã có:
@GetMapping(path = "/pages/health", produces = MediaType.TEXT_PLAIN_VALUE)
@ResponseBody
public String health() {
    return "UP";
}
~~~

Thêm imports:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.ResponseBody;
~~~

Sau đó `GET /pages/health` sẽ trả text `UP`. Phần fragment không tự biên dịch riêng vì nó phải nằm trong class `GreetingPageController`; đây là lựa chọn thiết kế, không cần bổ sung nếu project muốn giữ web-page controller thuần view.

Nếu toàn lớp đều trả dữ liệu máy đọc, dùng `@RestController` rõ nghĩa hơn. Nếu chỉ một số method cần body trong controller phục vụ trang, dùng method-level `@ResponseBody` để thể hiện ngoại lệ.

## 6. Kiểm tra qua HTTP: cùng dữ liệu, khác response

Sau khi khởi động ứng dụng:

~~~bash
curl -i 'http://localhost:8080/pages/greeting?name=Lan'
curl -i 'http://localhost:8080/api/greeting'
curl -i 'http://localhost:8080/api/message'
curl -i 'http://localhost:8080/api/redirect-text'
curl -i 'http://localhost:8080/pages/home'
~~~

Các kết quả chính:

| URL | HTTP mặc định | Dạng response | Nội dung đáng quan sát |
| --- | --- | --- | --- |
| `/pages/greeting?name=Lan` | 200 | `text/html` | HTML từ `greeting.html`, có `<h1>Hello Lan</h1>` |
| `/api/greeting` | 200 | `application/json` | `{"id":7,"greeting":"Hello Lan"}` |
| `/api/message` | 200 | `text/plain` | `Hello Lan` |
| `/api/redirect-text` | 200 | `text/plain` | `redirect:/pages/greeting` |
| `/pages/home` | 302 thường gặp | header `Location` | Browser chuyển đến `/pages/greeting?name=Guest` |

Đây là kết quả theo code demo và cấu hình Spring Boot/Thymeleaf mặc định. Thứ tự header, charset và định dạng HTML đầy đủ có thể thay đổi theo template/version. Với redirect, dùng `curl -i` để thấy status/header và **không thêm `-L`** nếu muốn quan sát 302 trước khi client tự follow.

`@ResponseBody` không yêu cầu status mặc định là 201 hay 204; nếu method bình thường hoàn thành và không thay status, Spring thường trả 200. Hãy trả status có chủ đích khi xây API tạo/xóa tài nguyên.

## 7. MockMvc: kiểm tra view, body, media type và redirect

Viết test dựa trên toàn bộ ứng dụng để có Thymeleaf view resolver thực sự. `src/test/java/com/example/responsedemo/web/GreetingControllerTest.java`:

~~~java
package com.example.responsedemo.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void controllerStringIsViewName() throws Exception {
        mvc.perform(get("/pages/greeting").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(view().name("greeting"))
                .andExpect(model().attribute("name", "Lan"))
                .andExpect(content().string(containsString("<h1>Hello Lan</h1>")));
    }

    @Test
    void restControllerDtoIsJsonBody() throws Exception {
        mvc.perform(get("/api/greeting").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.greeting").value("Hello Lan"));
    }

    @Test
    void restControllerStringIsPlainTextBody() throws Exception {
        mvc.perform(get("/api/message").accept(MediaType.TEXT_PLAIN))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_PLAIN))
                .andExpect(content().string("Hello Lan"));
    }

    @Test
    void redirectPrefixIsLiteralTextInRestController() throws Exception {
        mvc.perform(get("/api/redirect-text"))
                .andExpect(status().isOk())
                .andExpect(content().string("redirect:/pages/greeting"));
    }

    @Test
    void redirectPrefixInMvcControllerTriggersRedirect() throws Exception {
        mvc.perform(get("/pages/home"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/pages/greeting?name=Guest"));
    }

    @Test
    void incompatibleAcceptOnJsonMappingIsNotAcceptable() throws Exception {
        mvc.perform(get("/api/greeting").accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Mẫu test cố ý kiểm tra **cả trạng thái, media type, view name, model và body**. Nếu chỉ kiểm tra status 200, một route trả nhầm body string thành tên view vẫn có thể bị bỏ sót nếu view đó tình cờ tồn tại.

Một vài lưu ý:
- `@SpringBootTest` khởi tạo context đầy đủ để view resolver/template có mặt; kiểm tra view bằng `@WebMvcTest` riêng có thể yêu cầu thêm auto-configuration/beans phù hợp.
- Nếu ứng dụng có Spring Security, filters, hoặc nhiều `@ControllerAdvice`, MockMvc phải cấu hình chứng thực và error contract tương ứng. Đây là thay đổi của môi trường test, không phải bản chất `@ResponseBody`.
- Test `406` có thể phụ thuộc tùy chỉnh content negotiation/converter. Với `produces=application/json` rõ ràng như demo, `Accept=application/xml` không tương thích nên 406 là kỳ vọng hợp lý.
- Không dựa vào nội dung HTML đầy đủ hay thứ tự HTTP header như hợp đồng bất biến; tập trung vào nội dung và metadata quan trọng.

## 8. Khi cần redirect thật từ một API

Sai nếu dùng literal view prefix trong REST method:

~~~java
@RestController
class WrongRedirectController {
    @GetMapping("/wrong-redirect")
    public String wrongRedirect() {
        return "redirect:/pages/greeting";
    }
}
~~~

Kết quả sẽ là **body chuỗi**, không phải HTTP redirect. Để có 302/303 và `Location` cụ thể, dùng `ResponseEntity` trong REST controller:

~~~java
// Fragment trong @RestController đã import các class tương ứng:
@GetMapping("/go")
public ResponseEntity<Void> go() {
    return ResponseEntity.status(302)
            .location(URI.create("/pages/greeting"))
            .build();
}
~~~

Cần import `java.net.URI`, `org.springframework.http.ResponseEntity`. 302 chỉ là ví dụ; sau POST khi muốn chuyển client đến tài nguyên khác, **303 See Other** thường thể hiện rõ yêu cầu dùng GET ở URL đích. Không dùng Java `String` để đoán status HTTP.

Với page controller, `return "redirect:/..."` đơn giản, gắn với flow MVC/view. Với REST API, trả `ResponseEntity` và URL/Location rõ ràng giúp client HTTP hiểu ngay protocol semantics.

`forward:` trong `@Controller` cũng có ý nghĩa view special prefix đối với cấu hình view resolver hỗ trợ nó. Khi trả từ `@RestController` dưới dạng `String`, đây chỉ là literal body. Forward là server-side request dispatch, **khác HTTP redirect** mà trình duyệt nhìn thấy.

## 9. Những trường hợp dễ gây nhầm lẫn khác

### 9.1. Model/View và body không thay thế nhau

~~~java
@Controller
class ReportController {
    @GetMapping("/reports")
    public String reports(Model model) {
        model.addAttribute("count", 5);
        return "reports";
    }
}
~~~

`model.addAttribute` phục vụ view rendering, **không tự tạo JSON body** chứa `{"count":5}`. Muốn API JSON thì trả DTO, `Map` dưới `@ResponseBody`, hoặc `ResponseEntity`; còn `@Controller` trả `Map` mà không bật body semantics có thể được hiểu là bổ sung model attributes và chọn view.

### 9.2. `ModelAndView` và `View` là kiểu đặc biệt

`ModelAndView` thường mang view name (hoặc `View` instance), model và optional status. Nó có return handler riêng. Không khẳng định rằng **mọi** đối tượng Java trả từ `@RestController` đều luôn bị JSON serialize: framework xét **các return handler đặc biệt** trước tùy chữ ký/annotation. Tuy nhiên, để mã dễ đọc, các handler nhằm render template nên thuộc `@Controller`, còn API DTO/body nên thuộc `@RestController`.

### 9.3. `void`, `null` và servlet response

Method return `void` hoặc `null` có nhiều ngữ cảnh: đã tự ghi `HttpServletResponse`, có `@ResponseStatus`, đã đáp ứng ETag/Last-Modified hoặc chuyển sang default view name. Với REST handler, body có thể rỗng. Vì vậy **không coi `null` là lệnh trả 404 hay 204**. Trả `ResponseEntity.noContent().build()` cho 204, `ResponseEntity.notFound().build()` cho 404 khi đó là ý định API.

### 9.4. `@RequestBody` và `@ResponseBody` khác chiều

| Annotation | Vị trí chủ yếu | Dòng dữ liệu |
| --- | --- | --- |
| `@RequestBody` | Tham số handler | **HTTP request body → Java object** qua converter |
| `@ResponseBody` | Method/class controller | **Java return value → HTTP response body** qua converter |

Tương tự tên gọi nhưng không đồng nghĩa. Có thể dùng cả hai trên một REST endpoint POST: nhận JSON request và xuất JSON response, nhưng chỉ cần `@RestController` để thay `@ResponseBody` mức lớp.

### 9.5. Có cần template engine cho tất cả `@Controller`?

Không. `@Controller` chỉ là loại component web. Template engine hoặc view resolver cần thiết **khi method dùng view rendering**. Một `@Controller` thuần nhận request rồi trả `ResponseEntity` vẫn hoạt động mà không có Thymeleaf. Nếu method trả tên view nhưng project không có view technology được cấu hình phù hợp, đó mới là chỗ cần kiểm tra resolver/template.

### 9.6. Vì sao REST endpoint trả string nhưng Postman hiển thị JSON?

Một số công cụ UI cố parse/display theo header hoặc tự suy đoán. Hãy kiểm tra **byte body thực tế** và `Content-Type` qua curl hoặc integration test. `"hello"` dưới Java `String` có thể được ghi là `hello` không có dấu ngoặc kép; JSON scalar string hợp lệ phải có dấu ngoặc kép, ví dụ `"hello"` (nội dung HTTP có cặp dấu quote).

Nếu client bắt buộc nhận cấu trúc JSON, dùng DTO như `new MessageDto("hello")` → `{"message":"hello"}`, cách này rõ ràng hơn với API contract, công cụ sinh tài liệu và versioning.

## 10. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân thường gặp | Kiểm tra / sửa |
| --- | --- | --- |
| Trả `"ok"` nhưng gặp lỗi view/template | `@Controller` trả `String` được hiểu là tên view | Thêm `@ResponseBody` hoặc dùng `@RestController` cho API |
| Muốn HTML nhưng thấy chữ `home` | `@RestController` hoặc `@ResponseBody` khiến literal string được ghi body | Dùng `@Controller`, đảm bảo view resolver/template |
| Trả `"redirect:/login"` nhưng status 200 và body literal | Return nằm trong `@RestController` | Dùng `@Controller` redirect view hoặc `ResponseEntity` status + Location |
| Không tìm thấy template / HTTP 500 | Sai tên view, template path, thiếu Thymeleaf/JSP config | Đối chiếu `return "viewName"` với resolver/template |
| DTO không thành JSON | Thiếu Jackson/converter, lỗi serialize, media type không phù hợp | Kiểm dependency/converter, DTO và `Accept`/`produces` |
| 406 khi request JSON API | `Accept` không tương thích `produces` | Chỉnh `Accept` hoặc representation được hỗ trợ |
| Response hiển thị text trong khi header tuyên bố JSON | Trả `String` raw hoặc custom converter/produces lệch | Dùng DTO để serializer tạo JSON hợp lệ |
| JSON vô tình lộ thông tin nội bộ | Trả entity trực tiếp với các property không mong muốn | Tạo response DTO, kiểm soát serialization |
| Body rỗng nhưng frontend mong object | Method return `null`/`void` hoặc response 204 | Thiết kế status và response schema rõ ràng |
| Endpoint có response body nhưng class là `@Controller` | Method trả `ResponseEntity` hoặc có `@ResponseBody` | Đây là cơ chế hợp lệ; đọc return type/annotation trước khi kết luận |

Khi debug, kiểm tra cùng lúc **annotation ở type và method**, **return type**, **status**, **Content-Type**, **body bytes**, **view resolver** và **request Accept**. Những thành phần này thường giải thích hành vi mà chỉ nhìn Java `return` sẽ bỏ sót.

## 11. Chọn cách thiết kế theo ý định ứng dụng

**Ứng dụng server-rendered HTML:** dùng `@Controller`, method trả logical view name hoặc `ModelAndView`, dùng `Model` và template/view technology. Nếu vài endpoint nhỏ phải trả text/data, đặt `@ResponseBody` trên từng method tương ứng.

**REST API trả DTO:** dùng `@RestController` để mặc định serialize body; trả record/DTO và dùng `ResponseEntity<T>` khi cần điều khiển status/header. Định nghĩa `produces` khi API phải công bố media type cụ thể; viết test tương thích `Accept`.

**Controller hỗn hợp HTML/API:** có thể dùng `@Controller` cho template và `@ResponseBody`/`ResponseEntity` cho endpoints dữ liệu, nhưng nếu phạm vi đủ lớn, tách thành page controller và API controller giúp hành vi hiển nhiên hơn. Không cố dùng những chuỗi có tiền tố `redirect:` trong API controller để điều khiển HTTP.

**Lưu ý bảo mật:** View technologies và JSON converter có cách escape/serialize khác nhau. Thymeleaf `th:text` escape HTML; JSON serialization xử lý escaping theo chuẩn JSON. Không nối HTML trực tiếp từ dữ liệu request rồi trả `@ResponseBody String` và cho rằng nó có cùng các bảo vệ của template.

## 12. Tóm lược qua câu hỏi tự kiểm tra

**Câu 1.** Vì sao `@Controller` trả `"home"` không có `@ResponseBody` thường không gửi body `home`?

**Trả lời:** `String` được giải thích là logical view name, cần `ViewResolver` và view render.

**Câu 2.** `@RestController` có đồng nghĩa response luôn là JSON không?

**Trả lời:** Không. Nó kích hoạt body semantics ở cấp lớp; converter + type + media negotiation quyết định representation. `String` có thể là plain text.

**Câu 3.** `@Controller` trả `ResponseEntity<MyDto>` có phải thêm `@ResponseBody` không?

**Trả lời:** Không. `ResponseEntity` có return value handling riêng cho status, headers và body.

**Câu 4.** Làm sao redirect thực sự từ `@RestController`?

**Trả lời:** Dùng status 3xx và header `Location`, ví dụ `ResponseEntity.status(302).location(uri).build()`.

**Câu 5.** Một DTO Java được serialize JSON bởi thành phần nào?

**Trả lời:** Trong Spring MVC, return handler cho response body gọi `HttpMessageConverter`, thường Jackson JSON converter trong web starter.

**Câu 6.** Muốn chắc chắn một endpoint là view, cần test gì?

**Trả lời:** Kiểm `view().name(...)`, model attributes và HTML render; với body endpoint kiểm byte text/JSON, Content-Type và status.

## 13. Tài liệu chính thức

- [Spring Framework 6.2 — `@ResponseBody`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responsebody.html): annotation ở method/class, `HttpMessageConverter` và `@RestController`.
- [Spring Framework 6.2 — Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/return-types.html): các kiểu `String` view name, `View`, `ModelAndView`, `ResponseEntity`, `@ResponseBody`.
- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): các converter và kiểu body.
- [Spring Framework 6.2 — Mapping Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html): `produces`, `consumes` và HTTP content negotiation.
- [Spring Framework 6.2 — View Resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-core/viewresolver.html): vai trò `ViewResolver` trong render HTML.
- [Spring Boot — Spring MVC with Template Engines](https://docs.spring.io/spring-boot/reference/web/servlet.html): Spring MVC auto-configuration và template engines.

**Nguyên tắc chốt:** khi method trả `String`, đừng đoán behavior từ Java type. Hãy xác định **return handler được chọn**: `@Controller` thường đưa `String` đến **ViewResolver**, còn `@ResponseBody`/`@RestController` đưa return value đến **HttpMessageConverter**. Từ đó mới suy ra response thực tế và viết test đúng.

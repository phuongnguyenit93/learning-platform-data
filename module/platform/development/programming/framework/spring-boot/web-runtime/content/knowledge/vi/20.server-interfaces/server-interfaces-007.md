# Khả năng dựng view của MVC và WebFlux theo template engine

## 1. Dựng view phía máy chủ là gì?

Trong ứng dụng web, server có thể trả về JSON để frontend tự dựng giao diện, gửi sẵn tài nguyên HTML tĩnh, hoặc **kết hợp dữ liệu với một HTML template để tạo HTML động** trước khi trả về client. Cách cuối gọi là *server-side view rendering*.

Ví dụ trình duyệt gửi `GET /hello?name=Mai`. Controller chuẩn bị model `visitor = "Mai"`, chọn template `welcome.html`, engine thay dữ liệu vào vị trí thích hợp và trả một response có nội dung HTML. Trình duyệt nhận HTML cuối cùng, **không cần hiểu cú pháp Thymeleaf/FreeMarker**.

Hai stack web của Spring Boot đều có thể thực hiện công việc này:

- **Spring MVC (Servlet):** `DispatcherServlet` điều phối handler, kết hợp `Model` + tên view, rồi dùng `ViewResolver` và `View` để render.
- **Spring WebFlux (Reactive):** `DispatcherHandler` điều phối handler, `ViewResolutionResultHandler` giải quyết tên view/model, và một `View` kiểu reactive thực hiện việc ghi response theo hợp đồng `Mono<Void>`.

Cả hai có thể dùng **Thymeleaf**, **FreeMarker**, **Mustache**. Khác biệt lớn nằm ở pipeline HTTP, kiểu trả về, và cách chuẩn bị model dữ liệu bất đồng bộ; bản thân HTML template có thể giống nhau.

**Mục tiêu:** biết cách chọn engine, viết controller và template chạy được trên MVC/WebFlux, hiểu hạn chế của rendering trong môi trường reactive và xử lý lỗi, hiệu năng, escaping cho giao diện HTML.

## 2. Phân biệt view, model, template và JSON body

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Model** | Dữ liệu để view tiêu thụ; thường là các cặp tên–giá trị | `visitor = "Mai"`, `courses = List.of(...)` |
| **Tên view logic** | Tên mà controller yêu cầu render | `"welcome"` |
| **ViewResolver** | Tìm View phù hợp với tên logic, locale/media type/cấu hình | Ánh xạ `welcome` đến template Thymeleaf |
| **Template** | Mẫu HTML/text có expression và cấu trúc lặp/điều kiện | `src/main/resources/templates/welcome.html` |
| **Template engine** | Xử lý template và model để tạo HTML/text | Thymeleaf, FreeMarker, Mustache |
| **View** | Hợp đồng framework dùng để render mô hình thành HTTP response | MVC `org.springframework.web.servlet.View`; WebFlux `org.springframework.web.reactive.result.view.View` |
| **HTTP response** | Status, headers và body client thực sự nhận | `200 OK`, `Content-Type: text/html`, HTML bytes |

**Quan trọng:** method `@Controller` trả `String "welcome"` thường được coi là **tên view**; method ở `@RestController` (tương đương `@Controller` + `@ResponseBody`) trả `"welcome"` sẽ ghi **chuỗi đó thành body**, không tra `welcome.html`.

```java
// Render HTML bằng ViewResolver (đặt trong @Controller):
@GetMapping("/page")
public String page(Model model) {
    model.addAttribute("visitor", "Mai");
    return "welcome";
}

// Trả dữ liệu dạng text (đặt trong @RestController hoặc gắn @ResponseBody):
@GetMapping("/text")
@ResponseBody
public String text() {
    return "welcome";
}
```

Hai method trên là **mã minh họa trong các controller phù hợp**, không phải một file Java độc lập. Sự khác nhau đến từ `@ResponseBody`, không phải chỉ vì kiểu trả về cùng là `String`. Với `ResponseEntity<String>` hoặc `@ResponseBody`, framework xử lý body theo message converters/codecs; còn view cần bước resolve/render.

## 3. Template engines và mức hỗ trợ theo Spring Boot 3.3

Spring Boot tự cấu hình view khi starter template phù hợp có mặt trên classpath, trừ khi app đã ghi đè cấu hình.

| Công nghệ | Spring MVC | Spring WebFlux | Ghi chú |
|---|---|---|---|
| **Thymeleaf** | Có, qua tích hợp Thymeleaf Spring MVC | Có, qua tích hợp Thymeleaf Reactive | Dùng HTML template tự nhiên, `th:text`, `th:each`, `th:if` |
| **FreeMarker** | Có | Có | WebFlux không hỗ trợ đầy đủ tất cả tính năng FreeMarker như Servlet stack; kiểm tra feature cụ thể |
| **Mustache** | Có | Có | Template logic tối giản, hợp nhu cầu chèn dữ liệu cơ bản |
| **Groovy Markup Templates** | Boot có auto-configuration cho MVC | Không nằm trong danh sách template engines được Boot 3.3 tự cấu hình cho WebFlux | Tránh suy đoán tự dùng được ở reactive stack chỉ vì có dependency |
| **JSP/JSTL** | Thuộc hệ Servlet/MVC với một số giới hạn khi đóng gói embedded server | Không hỗ trợ theo kiểu JSP của Servlet | WebFlux không dùng Servlet/JSP rendering pipeline |

Starter điển hình: `spring-boot-starter-thymeleaf`, `spring-boot-starter-freemarker`, `spring-boot-starter-mustache`. Với cấu hình mặc định, Boot tìm các template từ `src/main/resources/templates`. Đừng trộn nhiều template engine chỉ để giải quyết cùng một tên view nếu không thật sự cần; có thể tạo nhiều resolver và thứ tự chọn view khó hiểu.

Ở ứng dụng dùng **`spring-boot-starter-web`**, Boot thường chọn MVC/Servlet. Với **`spring-boot-starter-webflux`** (và không có starter web), Boot chọn reactive WebFlux. Khi cả hai cùng xuất hiện, Boot thường ưu tiên Servlet/MVC mặc định; thêm `WebClient` không tự chuyển server sang reactive.

Cần phân biệt **template engine** và **HTTP stack**: Thymeleaf không tự biến MVC thành non-blocking; thêm FreeMarker cũng không tự biến WebFlux thành Servlet. Template là cách sinh nội dung, stack là cách xử lý request/response.

## 4. Spring MVC giải quyết view ra sao?

```text
Browser GET /hello
       │
       ▼
Tomcat/Jetty → Servlet Filter → DispatcherServlet
                                │
                                ▼
                     HandlerMapping / HandlerAdapter
                                │
                                ▼
                          @Controller
                  model.addAttribute("visitor", ...)
                  return "welcome"
                                │
                                ▼
                     ViewResolver (logical name)
                                │
                                ▼
             ThymeleafView / FreeMarkerView / ...
                                │
                                ▼
                    Template + model → HTML
                                │
                                ▼
                         HTTP 200 + HTML
```

Cụ thể:

1. `DispatcherServlet` nhận request đã qua container/filter.
2. Spring chọn handler, bind tham số/path variables, gọi controller.
3. Controller có thể đưa dữ liệu vào `Model`/`ModelMap` hoặc trả `ModelAndView`. Một `String` từ `@Controller` thường là tên view.
4. `ViewResolver` xác định `View` theo tên logic, locale và cấu hình. Với Thymeleaf, ví dụ `welcome` dẫn tới `classpath:/templates/welcome.html` theo cấu hình mặc định.
5. View xử lý template và model; kết quả ghi vào `HttpServletResponse`, cùng status/headers phù hợp.

Nếu controller trả `ModelAndView`, nó gộp tên view và model trong cùng đối tượng. `redirect:/target` trong MVC thường tạo redirect response (thay vì render template ở request hiện tại). Nếu một handler trả `@ResponseBody` thì bước view resolution ở trên được bỏ qua.

Quá trình render template có thể tiêu thụ CPU, tạo nhiều object, gọi các expression/formatter, và trong các thiết kế kém còn truy vấn dữ liệu ngay từ view. Tách việc truy vấn và chuẩn bị DTO ra service/controller để template chỉ nhận dữ liệu cần hiển thị.

## 5. Spring WebFlux giải quyết view ra sao?

WebFlux cũng có khái niệm tên view + model, nhưng dùng các thành phần reactive:

```text
Browser GET /hello
       │
       ▼
HTTP server (thường Reactor Netty)
       │
       ▼
WebFilter → DispatcherHandler
                 │
                 ▼
        HandlerMapping / HandlerAdapter
                 │
                 ▼
          @Controller trả:
          Mono<Rendering>
                 │
                 ▼
      ViewResolutionResultHandler
                 │
                 ▼
     Reactive ViewResolver / View
                 │
                 ▼
    Model + template → HTML response
```

Những kiểu trả về đáng biết trong `@Controller` WebFlux:

- `String`: tên view logic nếu không có `@ResponseBody`.
- `Mono<String>`: tên view được phát bất đồng bộ; cần tránh nhầm với JSON/text nếu không đánh dấu `@ResponseBody`.
- `Rendering` hoặc `Mono<Rendering>`: đối tượng ghép tên view, model, status và headers; đây là API `org.springframework.web.reactive.result.view.Rendering`, có vai trò tương tự `ModelAndView` trong MVC.
- `Model` hoặc các model attributes: dữ liệu cho template; WebFlux hỗ trợ một số reactive values trong model và chờ chúng được resolve theo hợp đồng framework.
- Với WebFlux functional endpoints, `ServerResponse.ok().render("welcome", model)` trả một `Mono<ServerResponse>` để render view.

**Reactive server không có nghĩa mọi template engine đều stream HTML theo từng phần tử.** Nhiều engine/kiểu view tạo HTML từ model đã đủ dữ liệu, rồi mới ghi response. Một `Flux` đưa vào model có thể cần thu thập hoặc xử lý theo cơ chế riêng của engine. Không mặc định template sẽ phát từng dòng HTML ngay khi Flux emit. Thymeleaf có tích hợp reactive/streaming chuyên biệt, nhưng cần cấu hình và loại model phù hợp; các ví dụ cơ bản bên dưới là **render một trang hoàn chỉnh**.

Điểm khác MVC là controller có thể chờ dữ liệu non-blocking bằng `Mono` rồi mới tạo `Rendering`; không cần gọi `block()` trên Netty event-loop chỉ để có dữ liệu cho trang.

## 6. Ví dụ hoàn chỉnh A: Spring MVC + Thymeleaf

Một project độc lập Java 17+, Spring Boot 3.3.13, Gradle. Request `GET /hello?name=Mai` render `welcome.html` với tên người dùng và danh sách môn học.

**Cấu trúc:**

```text
mvc-view-demo/
├── build.gradle
└── src/main/
    ├── java/com/example/mvcview/MvcViewApplication.java
    └── resources/
        ├── application.properties
        └── templates/welcome.html
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

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
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8080
# Dùng cấu hình mặc định Thymeleaf:
# spring.thymeleaf.prefix=classpath:/templates/
# spring.thymeleaf.suffix=.html
```

**`src/main/java/com/example/mvcview/MvcViewApplication.java`:**

```java
package com.example.mvcview;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@SpringBootApplication
public class MvcViewApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcViewApplication.class, args);
    }
}

@Controller
class HtmlPageController {

    @GetMapping("/hello")
    public String hello(
            @RequestParam(defaultValue = "Lan") String name,
            Model model) {

        model.addAttribute("visitor", name);
        model.addAttribute("courses", List.of("Java", "Spring MVC", "Thymeleaf"));
        return "welcome"; // Tên view, KHÔNG phải response text.
    }

    @GetMapping("/plain")
    @ResponseBody
    public String plain() {
        return "welcome"; // Body text do @ResponseBody.
    }
}
```

File trên có một top-level `public class` là `MvcViewApplication`; `HtmlPageController` là class package-private hợp lệ trong cùng file. Boot component scan bắt được controller vì nằm cùng package với application.

**`src/main/resources/templates/welcome.html`:**

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Trang chào mừng</title>
</head>
<body>
    <main>
        <h1 th:text="|Xin chào, ${visitor}!|">Xin chào!</h1>
        <p>Các chủ đề đang học:</p>
        <ul>
            <li th:each="course : ${courses}"
                th:text="${course}">Khóa học</li>
        </ul>
    </main>
</body>
</html>
```

Cú pháp của Thymeleaf:

- `th:text` đặt text vào phần tử HTML và **escape** các ký tự đặc biệt trong dữ liệu để tránh biến text thành HTML nguy hiểm.
- `|...${visitor}...|` là *literal substitution* của Thymeleaf, kết hợp text và expression.
- `th:each` lặp qua danh sách `courses`; `th:text` bên trong hiển thị từng phần tử.
- `xmlns:th` giúp template/IDE nhận biết namespace `th`, nhưng trình duyệt không cần thực thi Thymeleaf; server đã render xong.

**Chạy và kiểm tra:**

```bash
gradle bootRun
```

Trong project có Gradle Wrapper, có thể dùng `./gradlew bootRun` trên macOS/Linux hoặc `.\gradlew.bat bootRun` trên Windows PowerShell. Dùng JDK 17+, Gradle tương thích với Spring Boot 3.3.

```bash
curl -i "http://localhost:8080/hello?name=Mai"
curl -i "http://localhost:8080/plain"
```

Request `/hello?name=Mai` dự kiến nhận **HTTP 200**, `Content-Type` thuộc `text/html`, và HTML đã render chứa các đoạn:

```html
<h1>Xin chào, Mai!</h1>
<li>Java</li>
<li>Spring MVC</li>
<li>Thymeleaf</li>
```

Những dòng HTML trên là **trích đoạn đầu ra**, không phải toàn bộ body; whitespace và formatting có thể khác. Request `/plain` trả chuỗi body `welcome` thay vì HTML từ template. Nếu yêu cầu `/hello` không truyền `name`, Thymeleaf sẽ hiển thị `Xin chào, Lan!`.

**Đường đi thực tế:** request → controller `hello` → thêm `visitor`/`courses` vào model → trả tên view `welcome` → ThymeleafViewResolver tìm `welcome.html` → template sinh HTML → response cho browser. Đó là server-side rendering; source template `th:*` không được gửi để trình duyệt thực thi.

## 7. Ví dụ hoàn chỉnh B: Spring WebFlux + Thymeleaf

Bài tiếp theo dùng **project riêng**, tránh thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux` rồi vô tình chạy MVC. HTML template giống ví dụ A để thấy rằng phần thay đổi chủ yếu là controller/pipeline.

**Cấu trúc:**

```text
webflux-view-demo/
├── build.gradle
└── src/main/
    ├── java/com/example/fluxview/FluxViewApplication.java
    └── resources/
        ├── application.properties
        └── templates/welcome.html
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8081
```

**`src/main/java/com/example/fluxview/FluxViewApplication.java`:**

```java
package com.example.fluxview;

import java.time.Duration;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.reactive.result.view.Rendering;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class FluxViewApplication {

    public static void main(String[] args) {
        SpringApplication.run(FluxViewApplication.class, args);
    }
}

@Controller
class ReactivePageController {

    @GetMapping("/hello")
    public Mono<Rendering> hello(
            @RequestParam(defaultValue = "Lan") String name) {

        return Mono.delay(Duration.ofMillis(20))
                .map(tick -> Rendering.view("welcome")
                        .modelAttribute("visitor", name)
                        .modelAttribute(
                                "courses",
                                List.of("Java", "Spring WebFlux", "Thymeleaf"))
                        .build());
    }

    @GetMapping("/plain")
    @ResponseBody
    public Mono<String> plain() {
        return Mono.just("welcome");
    }
}
```

**`src/main/resources/templates/welcome.html`:** sử dụng lại **toàn bộ** HTML template ở ví dụ A, không đổi cú pháp. Đây là project độc lập nên vẫn phải tạo file `welcome.html` trong thư mục `templates` của project B.

`Mono.delay(Duration.ofMillis(20))` ở đây chỉ **mô phỏng dữ liệu tới bất đồng bộ**, không yêu cầu DB. Sau khi Mono phát tín hiệu, `Rendering.view("welcome")` gói tên view và model; WebFlux sẽ render sang HTML bằng Thymeleaf integration. Trong ứng dụng thực tế thay timer bằng nguồn non-blocking như `WebClient` hoặc R2DBC, và xử lý timeout/lỗi phù hợp.

**Chạy và kiểm tra:**

```bash
gradle bootRun
```

Nếu chạy cả hai project đồng thời, mỗi project có cổng riêng theo ví dụ. Với WebFlux ở cổng 8081:

```bash
curl -i "http://localhost:8081/hello?name=Mai"
curl -i "http://localhost:8081/plain"
```

Request `/hello?name=Mai` dự kiến **HTTP 200 + HTML**, có `Xin chào, Mai!` và các dòng `Java`, `Spring WebFlux`, `Thymeleaf`. Request `/plain` trả body text `welcome` (không resolve template) vì `@ResponseBody`.

Dù return type `Mono<Rendering>` là reactive, điều đó **không đảm bảo mỗi phần tử HTML được stream độc lập**. Ở ví dụ đơn giản, model được giải quyết, template render thành trang HTML rồi ghi response. Bất kỳ xử lý template tốn CPU hoặc lời gọi chặn trong template vẫn là chi phí cần quản lý.

## 8. WebFlux functional endpoints cũng render được view

Ngoài `@Controller`, WebFlux hỗ trợ functional routing với `RouterFunction<ServerResponse>`. `ServerResponse.ok().render(...)` là đường trực tiếp từ handler function tới view renderer.

Ví dụ **bổ sung vào một class `@Configuration` trong project WebFlux** (đoạn dưới là class hoàn chỉnh):

```java
package com.example.fluxview;

import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration
class FunctionViews {

    @Bean
    RouterFunction<ServerResponse> viewRoutes() {
        return route(GET("/functional"), request ->
                ServerResponse.ok().render("welcome", Map.of(
                        "visitor", "Khách",
                        "courses", List.of("WebFlux.fn", "Thymeleaf"))));
    }
}
```

Lưu class này thành `FunctionViews.java` trong package `com.example.fluxview`, giữ template `welcome.html`. Truy cập `http://localhost:8081/functional` để render trang có lời chào `Khách`, cùng danh sách `WebFlux.fn` và `Thymeleaf`. `ServerResponse.ok().render(...)` trả một `Mono<ServerResponse>` mà framework quản lý.

**Đừng nhầm:** `ServerResponse.ok().bodyValue(map)` tạo response từ body (thường serialize JSON theo codec), còn `render(viewName, model)` yêu cầu view/template. Trong MVC annotated controller thường chọn tên view hoặc `ModelAndView`; trong WebFlux annotated controller thường chọn tên view hoặc `Rendering`; trong WebFlux.fn dùng `ServerResponse.render`.

## 9. Model bất đồng bộ và giới hạn thực tế của reactive rendering

Spring WebFlux có thể nhận dữ liệu non-blocking trước khi render:

```java
// Đoạn nằm trong một @Controller WebFlux;
// service.findProfile(id) trả Mono<Profile> thực sự được định nghĩa ở ứng dụng.
@GetMapping("/profiles/{id}")
public Mono<Rendering> profile(@PathVariable String id) {
    return service.findProfile(id)
            .map(profile -> Rendering.view("profile")
                    .modelAttribute("profile", profile)
                    .build());
}
```

Đây là **mảnh minh họa**, không phải file tự chạy: cần có `service`, `Profile`, template `profile.html` và import `PathVariable`/`Rendering`. Cách trên giữ dữ liệu không blocking và chỉ tạo rendering khi profile sẵn sàng.

Trong WebFlux, `Model` cũng có thể chứa reactive attributes như `Mono<Account>` (framework có khả năng resolve reactive values theo loại model/view). Nhưng không phải engine nào cũng hỗ trợ render **Flux vô hạn** theo cách bạn tưởng. Trước khi đưa `Flux` vào model, cần xét:

- Flux hữu hạn hay vô hạn?
- Có phải collect toàn bộ dữ liệu trước render? Nếu có, giới hạn bộ nhớ và số phần tử.
- View engine có thật sự cung cấp **reactive streaming/data driver** cho loại view và template đang dùng hay không?
- Nếu client disconnect, nguồn dữ liệu và cleanup có bị hủy đúng cách không?
- Rendering có dùng biểu thức gọi API blocking hoặc code nặng trên event-loop không?

**Không gọi `block()` trong controller WebFlux** chỉ để biến `Mono<Profile>` thành `Profile`. Nó có thể chặn event-loop và làm giảm khả năng xử lý đồng thời. Compose bằng `map`/`flatMap` rồi trả publisher như ví dụ.

Một template engine có thể dùng reactive API ở bên ngoài nhưng phần render có bước tạo HTML CPU-bound hoặc blocking trong nội bộ. WebFlux giảm nhu cầu chiếm thread khi **chờ I/O**, không loại bỏ chi phí CPU khi format HTML. Tránh khẳng định "Thymeleaf trên WebFlux luôn stream từng phần tử" hoặc "WebFlux render HTML luôn nhanh hơn MVC".

## 10. Cấu hình view resolver, template path và cache

Với Thymeleaf starter, Spring Boot 3.3 tự cấu hình nhiều thành phần thông dụng. Tên view `"welcome"` với cấu hình mặc định thường tìm ở `classpath:/templates/welcome.html`.

Ví dụ cấu hình phát triển:

```properties
spring.thymeleaf.prefix=classpath:/templates/
spring.thymeleaf.suffix=.html
spring.thymeleaf.encoding=UTF-8
spring.thymeleaf.cache=false
```

Đặt `cache=false` chỉ khi cần thấy thay đổi template thuận tiện trong development. Production thường nên bật cache để tránh tải và parse template quá nhiều lần. `cache` của template engine không đồng nghĩa HTTP cache tại browser/CDN; hai loại cache được cấu hình riêng.

Với FreeMarker, một số tùy chọn tương ứng là `spring.freemarker.template-loader-path`, `spring.freemarker.suffix` và `spring.freemarker.cache`. File template có thể dùng `.ftlh` theo cấu hình Boot FreeMarker phổ biến. Với Mustache, template mặc định dùng đuôi `.mustache` (và starter `spring-boot-starter-mustache`). **Không sao chép cấu hình resolver dành cho MVC sang WebFlux** nếu API khác package; ưu tiên cấu hình Boot theo starter thực sự dùng.

Hai interface configurer cũng khác nhau:

- MVC: `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`, các resolver/view của `org.springframework.web.servlet...`.
- WebFlux: `org.springframework.web.reactive.config.WebFluxConfigurer`, `org.springframework.web.reactive.result.view...`.

Khi cần custom FreeMarker, Spring MVC và WebFlux có cách đăng ký resolver riêng; ví dụ WebFlux có `configureViewResolvers(ViewResolverRegistry registry)` và `registry.freeMarker()`, kèm `FreeMarkerConfigurer` thích hợp. Với Thymeleaf trên WebFlux, integration riêng do Thymeleaf cung cấp (chẳng hạn `ThymeleafReactiveViewResolver`). Nếu starter Boot đã cung cấp bean cần thiết, không đăng ký bộ resolver mới chỉ để làm việc mà auto-configuration đã giải quyết.

Không thêm `@EnableWebMvc` hoặc `@EnableWebFlux` một cách máy móc khi dùng Boot: các annotation này trao quyền cấu hình nhiều phần cho ứng dụng, có thể làm thay đổi các tiện ích auto-configuration mặc định. Nếu chỉ cần một custom hook, dùng configurer hoặc properties.

## 11. Xử lý forms, fragments, redirects và status

Dựng HTML bằng template phù hợp với trang danh sách, form và HTML fragments.

**Forms:** Trong MVC, controller có thể thêm form-backing object vào model; Spring MVC/Thymeleaf có cơ chế binding và hiển thị lỗi validation. WebFlux annotated controllers cũng có model binding và validation, nhưng **kiểu dữ liệu và cơ chế bất đồng bộ khác**. Khi render form lỗi, model phải chứa cả giá trị đã gửi và thông tin lỗi; sử dụng CSRF protection phù hợp với ứng dụng có đăng nhập/session.

**Fragments:** Thymeleaf hỗ trợ tái sử dụng cấu trúc:

```html
<!-- templates/fragments/footer.html -->
<footer th:fragment="footer">
    <small>Bản quyền ví dụ</small>
</footer>
```

Một trang khác có thể dùng:

```html
<div th:replace="~{fragments/footer :: footer}"></div>
```

Hai mảnh HTML trên minh họa syntax fragment; phải tạo file footer tương ứng trong thư mục templates. Đây là khả năng **của Thymeleaf**, không do MVC/WebFlux riêng quyết định. Với HTML-over-the-wire/HTMX, có thể render fragment thay vì cả trang, nhưng cách trả nhiều fragments hoặc streaming chúng phụ thuộc phiên bản Spring Framework và contract của ứng dụng; đừng mặc định mọi dự án Boot 3.3 đều có cùng API fragment mới của các bản Framework cao hơn.

**Redirect:** MVC thường sử dụng tên view `"redirect:/dashboard"` để chỉ thị redirect. Với WebFlux annotated controller, `Rendering.redirectTo("/dashboard").build()` là một API rõ ràng; response redirect là status 3xx + `Location`, không render template dashboard ngay trên request ban đầu.

**Status/headers:** MVC có `ModelAndView`, `ResponseEntity`/`@ResponseStatus` và các cơ chế phù hợp từng return type. WebFlux `Rendering.view("...").status(HttpStatus.CREATED).header("X-...", "...").build()` có thể kèm status/headers theo API. Không giả định HTML view mặc định luôn trả 200, vì redirect, lỗi hoặc cấu hình có thể tạo status khác.

## 12. Escaping và ranh giới tin cậy trong template

Template là phần mã/logic phía server có thể truy cập object model và trong một số engine có thể truy cập bean/biểu thức quyền cao. **Không cho người dùng sửa hoặc chọn template expression tùy ý** rồi render với quyền của ứng dụng.

Ví dụ chuỗi query `name` do người dùng cung cấp có thể chứa `<script>...`. Với Thymeleaf:

- `th:text` chèn **text đã escape theo HTML**.
- `th:utext` chèn **HTML không escape**, chỉ phù hợp khi nội dung đã được kiểm soát/sanitized đúng hợp đồng và mục đích.
- Không lấy trực tiếp `?view=...` làm tên view mà không whitelist; có thể dẫn tới template selection, resource exposure hay expression/template injection tùy cấu hình.
- Không đưa secrets, session/token, internal DTO hoặc thông tin không dành cho trình duyệt vào model chỉ vì template đang hoạt động phía server.
- Với form có xác thực, dùng CSRF protections/cookies/headers theo framework và threat model; auto-escape HTML không thay thế authorization, CSRF hoặc kiểm tra URL nguy hiểm.

**HTML escaping theo context:** Chèn text vào nội dung phần tử, thuộc tính HTML, URL, JavaScript hoặc CSS có rủi ro khác nhau. Đặc biệt, không tự ghép dữ liệu người dùng vào JavaScript string hoặc `href="javascript:..."` rồi cho rằng `th:text` ở chỗ khác đã làm trang an toàn. Dùng expression/URL helper và validation phù hợp từng context.

Sự khác biệt security ở đây chủ yếu thuộc **cách dùng engine và nguồn dữ liệu**, không phải tuyên bố MVC luôn an toàn hơn hay WebFlux tự chặn XSS.

## 13. Hiệu năng và chiến lược chọn MVC hay WebFlux để render HTML

| Câu hỏi | Hướng suy nghĩ |
|---|---|
| Ứng dụng chủ yếu dựng vài trang HTML từ dữ liệu đồng bộ/JPA? | MVC + template engine thường đơn giản và phù hợp |
| Dữ liệu đến từ nhiều API/driver reactive thực sự? | WebFlux có lợi trong việc compose I/O bất đồng bộ, nhưng vẫn cần cân nhắc chi phí view render |
| Muốn HTML stream từng chunk như SSE hay HTML-over-the-wire? | Kiểm tra engine, loại renderer, API của đúng phiên bản framework; không giả định template chuẩn tự stream |
| Trang có danh sách rất lớn? | Phân trang/lazy load, tránh render hàng trăm nghìn node HTML trong một response |
| Template parse nhiều? | Cấu hình cache production và đo chi phí render, giữ template đơn giản |
| Template gọi database/API ngay khi evaluate? | Đưa truy vấn ra service trước khi render và giới hạn latency/concurrency |
| Cần SEO/HTML first load? | Server-rendered HTML hữu ích vì browser nhận nội dung HTML ngay, nhưng vẫn cần caching và tối ưu payload |

Không đánh giá WebFlux dựa trên tên "reactive" mà bỏ qua nguồn dữ liệu. Dùng JDBC blocking trực tiếp trên Reactor Netty event-loop làm hại throughput; nếu không có nguồn reactive thực sự, MVC có thể dễ triển khai, quan sát và vận hành hơn. Ngược lại, MVC cũng có hỗ trợ async request processing; không nên nói MVC "hoàn toàn không làm được async".

Ở hai stack, quyết định về SSR phụ thuộc trải nghiệm người dùng, yêu cầu SEO, vòng đời ứng dụng, chi phí render, tính sẵn có của template engines và hệ sinh thái dữ liệu. Một project có thể vừa render HTML vừa cung cấp JSON API; việc đó không yêu cầu phải tách thành hai web server.

## 14. Kiểm tra và phát hiện lỗi render

### 14.1. Kiểm tra nội dung HTTP thật

Sau khi start app, dùng:

```bash
curl -i "http://localhost:8080/hello?name=Lan"
curl -i "http://localhost:8081/hello?name=Lan"
```

Với cả hai ví dụ, phản hồi HTML phải có lời chào và các mục `Java`, `Spring ...`. Kiểm tra **body HTML đã được render**, không chỉ mã HTTP 200. Nếu ứng dụng trả literal `welcome`, xem controller có bị `@RestController`/`@ResponseBody` hay không.

### 14.2. Lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Browser nhận chữ `welcome` thay vì trang | Method thuộc `@RestController`/`@ResponseBody` nên chuỗi được ghi thành body | Đổi sang `@Controller` trả tên view, hoặc trả `Rendering` phù hợp |
| `TemplateInputException` / không thấy template | Sai đường dẫn, chữ hoa/thường, suffix/prefix, template không được package vào classpath | Xem `src/main/resources/templates`, tên file và cấu hình engine |
| Controller 200 nhưng body thiếu dữ liệu | Sai tên attribute, model chưa có giá trị, expression template sai | So khớp `model.addAttribute("visitor",...)` với `${visitor}` |
| Dùng Thymeleaf ở app không có starter | Chưa có resolver/engine trên classpath | Thêm `spring-boot-starter-thymeleaf` và kiểm tra dependency tree |
| Dự kiến WebFlux nhưng thực tế dùng MVC | Có cả `starter-web` lẫn `starter-webflux`, Boot ưu tiên Servlet | Kiểm tra dependencies và loại ApplicationContext |
| Template không cập nhật trong development | Cache template đang bật | Kiểm tra `spring.thymeleaf.cache=false` trong profile dev |
| Performance kém khi tải cao | Render quá nặng, model quá lớn, template truy vấn blocking | Đo render latency, profile CPU, phân trang, đưa I/O ra khỏi template |
| HTML injection/XSS | Dùng `th:utext` hay nối HTML không được kiểm soát | Chuyển sang `th:text` khi chỉ cần text, kiểm tra context escaping |
| WebFlux treo vì chờ dữ liệu | Có `block()` hoặc I/O đồng bộ trên event loop | Xem thread/trace, dùng Publisher non-blocking, tách blocking nếu bắt buộc |
| 404 khi truy cập static css | Static assets phải ở thư mục phù hợp, không phải template HTML | Kiểm tra `resources/static` và URL mapping của stack |
| Trang lỗi HTML khác mong đợi | Error view convention, handler, content negotiation khác nhau theo stack | Kiểm tra `error` templates và hướng dẫn Boot của MVC/WebFlux riêng |

### 14.3. Phân biệt HTML test với JSON test

Khi kiểm thử view, nên kiểm tra `Content-Type: text/html` và HTML đã render, không chỉ assert tên view. MVC có thể dùng `MockMvc` để kiểm tra view name và model; WebFlux có `WebTestClient` để kiểm tra HTTP thực tế. Với integration test chạy server thật, hai stack đều có thể dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` rồi gọi URL và assert response body. Test template engine bằng HTTP giúp phát hiện lỗi đường dẫn, model expression hoặc cấu hình view resolver mà unit test controller thuần túy có thể bỏ sót.

## 15. Các nhầm lẫn cần tránh

- **“WebFlux chỉ làm API JSON, không render HTML.”** Sai: WebFlux có view resolution và Thymeleaf/FreeMarker/Mustache.
- **“Chỉ thêm `spring-boot-starter-thymeleaf` là controller `@RestController` sẽ tự render.”** Sai: `@ResponseBody` ghi dữ liệu trực tiếp.
- **“Cùng template engine thì MVC và WebFlux có cùng lớp ViewResolver.”** Sai: các lớp/framework API khác package, dù cú pháp template có thể giống nhau.
- **“Mono<Rendering> bảo đảm HTML streaming từng element.”** Sai: reactive composition khác cơ chế output streaming của engine.
- **“Thymeleaf template chỉ được browser xử lý.”** Sai: engine xử lý trên server; browser nhận HTML kết quả.
- **“Sử dụng WebFlux đồng nghĩa mọi render không blocking.”** Sai: template rendering có thể tiêu thụ CPU hoặc chạy code đồng bộ.
- **“JSP phù hợp như nhau cho MVC và WebFlux.”** Sai: JSP gắn với Servlet stack; WebFlux không dùng JSP như view technology thông thường.
- **“`th:text` và `th:utext` có hiệu quả bảo vệ như nhau.”** Sai: `th:utext` đưa HTML không escape vào output.
- **“Tên view luôn là tên file nguyên vẹn.”** Sai: `ViewResolver` kết hợp logical name với prefix, suffix, locale và cấu hình khác.

## 16. Tài liệu tham khảo chính thức

1. Spring Boot 3.3, Servlet Web Applications — Template Engines và static resources: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
2. Spring Boot 3.3, Reactive Web Applications — Template Engines (Thymeleaf, FreeMarker, Mustache): https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
3. Spring Framework — MVC View Resolution: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/viewresolver.html
4. Spring Framework — MVC View Technologies: https://docs.spring.io/spring-framework/reference/web/webmvc-view.html
5. Spring Framework — WebFlux View Technologies (Thymeleaf/FreeMarker, ghi chú security): https://docs.spring.io/spring-framework/reference/web/webflux-view.html
6. Spring Framework 6.1 — API `Rendering` cho WebFlux: https://www.springframework.org/spring/docs/6.1.0-RC2/javadoc-api/org/springframework/web/reactive/result/view/Rendering.html
7. Thymeleaf — tài liệu sử dụng Spring và HTML escaping: https://www.thymeleaf.org/documentation.html

**Ghi nhớ:** MVC và WebFlux đều hỗ trợ server-side template rendering. Chọn đúng `@Controller` và tên view/`Rendering`, cung cấp model phù hợp, để resolver tìm template, và trả HTML đã render. Với WebFlux, non-blocking I/O giúp chuẩn bị dữ liệu bất đồng bộ, nhưng rendering/streaming thực tế còn phụ thuộc engine và thiết kế model; trong cả hai stack phải quan tâm escaping, cache và hiệu năng.
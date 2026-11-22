# Cấu hình công nghệ mẫu tương thích WebFlux

**Ngữ cảnh:** Spring Framework Reactive → **Hiển thị giao diện**.

Spring WebFlux không chỉ dùng để xây dựng REST API trả JSON. Ứng dụng WebFlux còn có thể tạo HTML động ở server bằng template engine, phục vụ file tĩnh, hoặc kết hợp backend reactive với một frontend SPA độc lập. Công nghệ render phải tích hợp với cơ chế view của Spring WebFlux và không phụ thuộc vào Servlet API theo cách chỉ có trong Spring MVC.

Các lựa chọn phổ biến:

- **FreeMarker:** Spring Framework có tích hợp view FreeMarker trực tiếp cho WebFlux; phù hợp HTML, email và text template. Một số tính năng FreeMarker không được hỗ trợ đầy đủ trong WebFlux.
- **Thymeleaf:** tích hợp WebFlux do dự án Thymeleaf quản lý, với `SpringWebFluxTemplateEngine` và `ThymeleafReactiveViewResolver`.
- **Mustache:** Spring Boot có auto-configuration cho Mustache trong ứng dụng WebFlux. Template logic nhẹ, dữ liệu được chuẩn bị trong controller/service.
- **Static HTML và SPA:** WebFlux phục vụ các file HTML, CSS, JavaScript đã build; phù hợp React, Vue, Angular hoặc frontend độc lập.
- **Script template hoặc ViewResolver tùy chỉnh:** Spring Framework có điểm mở rộng cho thư viện template chạy trên JSR-223 hoặc một `ViewResolver` do ứng dụng cung cấp.

`JSP` là công nghệ của Servlet stack, không phải lựa chọn view cho WebFlux. WebFlux không yêu cầu Servlet API, không dùng `src/main/webapp` và không triển khai theo mô hình WAR Servlet truyền thống.

## 1. Kiến trúc hiển thị giao diện trong WebFlux

Trong annotated controller, `DispatcherHandler` là front controller. Controller cung cấp tên view và model; `ViewResolutionResultHandler` tìm view tương ứng; template engine render HTML vào HTTP response.

```text
Browser request
      |
      v
WebFlux server adapter
      |
      v
DispatcherHandler
      |
      v
HandlerMapping / Controller
      |
      +---- model attributes
      |
      +---- logical view name: "home"
                    |
                    v
          ViewResolutionResultHandler
                    |
                    v
                ViewResolver
                    |
                    v
           FreeMarker / Thymeleaf /
                 Mustache
                    |
                    v
             Rendered HTML
                    |
                    v
              HTTP response
```

| Thành phần | Vai trò |
|---|---|
| `@Controller` | Xử lý request và trả view name hoặc `Rendering` |
| `Model` / `Rendering` | Chuyển dữ liệu cần hiển thị cho view |
| `ViewResolver` | Ánh xạ tên logic như `home` thành một View |
| `View` | Render model thành response |
| Template engine | Thay expression trong template bằng dữ liệu |
| `DispatcherHandler` | Điều phối handler và result handler của WebFlux |

`@RestController` bao gồm `@ResponseBody`. Nếu method trả về `String` trong `@RestController`, chuỗi được ghi vào response body; Spring không coi nó là tên template. Muốn render HTML bằng view resolution, dùng `@Controller` hoặc cấu hình một view/response rõ ràng.

## 2. Những công nghệ template được hỗ trợ

Spring Framework cho phép thay đổi view technology qua cấu hình `ViewResolver`. Spring Boot bổ sung auto-configuration cho các engine phổ biến khi dependency tương ứng có mặt.

| Công nghệ | Tích hợp với WebFlux | Đặc điểm và cách chọn |
|---|---|---|
| FreeMarker | Tích hợp built-in trong Spring Framework | `FreeMarkerConfigurer` và resolver; HTML/text template |
| Thymeleaf | Tích hợp do dự án Thymeleaf quản lý | Reactive engine và resolver; HTML, form, Spring EL |
| Mustache | Spring Boot auto-config hỗ trợ WebFlux | Logic nhẹ, model được chuẩn bị ở Java |
| Script template | Spring Framework hỗ trợ qua JSR-223 | Cần script engine và thư viện tương ứng |
| Custom ViewResolver | Có thể đăng ký trực tiếp | Dùng cho engine hoặc quy tắc render riêng |
| JSP/JSTL | Servlet stack | Không dùng trực tiếp làm view engine WebFlux |

Spring Boot 3.5 hỗ trợ auto-configuration cho FreeMarker, Thymeleaf và Mustache. Với cấu hình mặc định, template được tìm trong `src/main/resources/templates`. Riêng FreeMarker, tài liệu Boot lưu ý không phải tất cả tính năng đều được hỗ trợ với WebFlux; hãy kiểm tra tính năng cụ thể trước khi dùng.

### 2.1. FreeMarker

FreeMarker có tích hợp trực tiếp trong Spring WebFlux. Các thành phần quan trọng khi tự cấu hình:

- `FreeMarkerConfigurer`: cấu hình template loader, settings, shared variables và encoding.
- `FreeMarkerViewResolver`: ánh xạ tên view tới template.
- `ViewResolutionRegistry.freeMarker()`: shortcut đăng ký resolver qua `WebFluxConfigurer`.

Ví dụ view name `welcome` có thể được resolve thành `classpath:/templates/freemarker/welcome.ftl` nếu loader path được cấu hình như vậy.

FreeMarker phù hợp với ứng dụng cần template HTML/text có biểu thức, điều kiện và vòng lặp. Với HTML, ưu tiên định dạng template có auto-escaping như hậu tố `.ftlh`; không tắt escaping một cách tùy tiện.

### 2.2. Thymeleaf

Thymeleaf tạo HTML từ template có thể mở trực tiếp trong trình duyệt để xem cấu trúc tĩnh. Tích hợp WebFlux thường dùng:

- `SpringResourceTemplateResolver`: tìm template trong resource của Spring.
- `SpringWebFluxTemplateEngine`: engine dành cho Spring WebFlux.
- `ThymeleafReactiveViewResolver`: kết nối engine với cơ chế view resolution reactive.

Tích hợp WebFlux do dự án Thymeleaf quản lý. Khi dùng Spring Boot, ưu tiên starter và auto-configuration tương thích với phiên bản Spring Framework của Boot. Nếu cấu hình thủ công, dùng đúng thư viện Spring integration; không lấy `ThymeleafViewResolver` của Spring MVC để cắm vào WebFlux.

Thymeleaf hữu ích khi cần `th:text`, `th:each`, `th:if`, form binding, message bundle và Spring EL. Template nên nằm trong ranh giới tin cậy của ứng dụng.

### 2.3. Mustache và script template

Mustache là template engine logic-light. Template tập trung vào hiển thị dữ liệu; điều kiện và xử lý nghiệp vụ nên nằm trong Java service/controller.

```html
<h1>{{pageTitle}}</h1>
<ul>
  {{#books}}
    <li>{{title}}</li>
  {{/books}}
</ul>
```

Spring Boot có auto-configuration cho Mustache trong WebFlux. Thêm starter tương ứng và đặt template trong thư mục mặc định. Khi cần điều kiện phức tạp, lọc dữ liệu hoặc tính toán, làm trong service và chuyển kết quả đơn giản sang model.

Spring Framework cũng hỗ trợ script view cho engine chạy trên JSR-223. Engine phải thực hiện các contract như `ScriptEngine` và `Invocable`. Cấu hình bằng `ScriptTemplateConfigurer`, chỉ định engine name, script, render function và resolver.

Không phải mọi JavaScript engine đều có sẵn trong JDK hiện đại. Nashorn đã bị loại khỏi JDK sau Java 14; nếu chọn engine JavaScript, phải thêm engine tương thích riêng. Với FreeMarker, Thymeleaf hoặc Mustache tiêu chuẩn, ưu tiên tích hợp sẵn.

## 3. Static HTML, SPA và server-side template

Ba hướng hiển thị có thể cùng tồn tại:

| Hướng | Backend trả về | Khi nào phù hợp |
|---|---|---|
| Server-side rendering (SSR) | HTML đã render từ template và model | Trang có nội dung theo request, form, trang quản trị |
| Static frontend / SPA | HTML/JS/CSS đã build; API trả JSON | Frontend độc lập, routing phía browser |
| Hybrid | Static assets, template và JSON API | Landing page SSR kết hợp màn hình SPA |

WebFlux có thể phục vụ static resource từ classpath:

```text
src/main/resources/
├── static/
│   ├── css/site.css
│   ├── js/app.js
│   └── images/logo.svg
├── templates/
│   └── home.ftlh
└── application.properties
```

Boot mặc định phục vụ static content từ `classpath:/static`, `classpath:/public`, `classpath:/resources` và `classpath:/META-INF/resources`. Tài nguyên thường được map trên `/**`. Có thể thay path bằng `spring.webflux.static-path-pattern` và thay vị trí bằng `spring.web.resources.static-locations`.

Ví dụ:

```properties
spring.webflux.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/static/
```

Khi thay `static-locations`, giá trị mới thay thế danh sách mặc định. Boot cũng hỗ trợ WebJars qua path mặc định `/webjars/**`, có thể đổi bằng `spring.webflux.webjars-path-pattern`.

Static resource không được render bằng FreeMarker hay Thymeleaf. Browser nhận nguyên file đã build. Với SPA, backend có thể phục vụ bundle frontend và cung cấp API WebFlux riêng; nếu frontend đặt ở origin khác, cấu hình CORS và authentication đúng cách.

## 4. Controller trả view name và model

Một controller dùng view resolution thường có dạng:

```java
@Controller
public class HomeController {

    @GetMapping("/")
    public String home(Model model) {
        model.addAttribute("pageTitle", "Trang chủ");
        return "home";
    }
}
```

`"home"` là logical view name, không phải đường dẫn file. `ViewResolver` chọn template tương ứng, ví dụ `home.ftlh`, `home.html` hoặc `home.mustache` tùy engine.

Có thể dùng `Rendering` để khai báo view và model rõ ràng:

```java
@Controller
public class HomeController {

    @GetMapping("/about")
    public Rendering about() {
        return Rendering.view("about")
                .modelAttribute("pageTitle", "Giới thiệu")
                .modelAttribute("version", "1.0")
                .build();
    }
}
```

`Rendering` thuộc package `org.springframework.web.reactive.result.view`. Nó cho phép chỉ định logical view, model attributes, status, headers và cookie. Nếu cần redirect, có thể dùng `Rendering.redirectTo("/home").build()`.

### 4.1. Model có thể chứa publisher reactive

WebFlux cho phép model chứa các kiểu reactive như `Mono` và `Flux`. Trước khi render, framework resolve các model attribute này thành giá trị cụ thể:

- `Mono<T>` được resolve thành một giá trị hoặc không có giá trị nếu empty.
- `Flux<T>` được thu thập thành `List<T>` trước khi view render.
- Publisher lỗi làm quá trình render thất bại theo error flow của request.

Ví dụ:

```java
@Controller
public class CatalogController {

    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/catalog")
    public Mono<Rendering> catalog() {
        return Mono.just(
                Rendering.view("catalog")
                        .modelAttribute(
                                "books",
                                catalogService.findAll())
                        .build());
    }
}
```

`catalogService.findAll()` trả `Flux<Book>`. WebFlux resolve publisher trong model trước khi render template. Điều này cho phép service tiếp tục dùng reactive API mà không gọi `block()` trong controller.

`Flux` trong model được collect thành list. Không đưa publisher vô hạn, SSE hoặc hàng triệu item vào model của một trang HTML; dùng pagination, giới hạn kết quả hoặc endpoint streaming riêng. View rendering không tự biến template thành stream HTML vô hạn.

## 5. Cấu hình Spring Boot với FreeMarker

Đối với ứng dụng Boot, thêm starter WebFlux và starter FreeMarker. Boot sẽ auto-configure view support phù hợp khi các dependency có mặt.

Cấu trúc project mẫu:

```text
webflux-template-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/TemplateApplication.java
    │   ├── java/demo/HomeController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── templates/home.ftlh
    │       └── static/css/site.css
    └── test/
        └── java/demo/HomePageIntegrationTest.java
```

### 5.1. pom.xml

Ví dụ dùng Java 17 và Spring Boot 3.5.16:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-template-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-freemarker</artifactId>
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

Spring Boot quản lý phiên bản FreeMarker tương thích qua dependency management. Tránh tự nâng riêng FreeMarker hoặc Spring Framework nếu chưa kiểm tra compatibility matrix của Boot.

### 5.2. TemplateApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TemplateApplication {

    public static void main(String[] args) {
        SpringApplication.run(TemplateApplication.class, args);
    }
}
```

### 5.3. application.properties

```properties
spring.application.name=webflux-template-demo
spring.freemarker.template-loader-path=classpath:/templates/
spring.freemarker.suffix=.ftlh
spring.freemarker.charset=UTF-8
spring.freemarker.cache=true
server.port=8080
```

Các thuộc tính này chỉ rõ nơi tìm template, hậu tố file, encoding và caching. Trong môi trường phát triển có thể tắt cache để tiện sửa template; trong production nên bật cache và đóng gói template bất biến cùng ứng dụng.

### 5.4. HomeController.java

```java
package demo;

import java.util.Map;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class HomeController {

    @GetMapping("/")
    public Mono<Rendering> home() {
        Flux<Map<String, String>> books = Flux.just(
                Map.of("title", "Reactive Streams"),
                Map.of("title", "Spring WebFlux"),
                Map.of("title", "Reactive Systems"));

        return Mono.just(
                Rendering.view("home")
                        .modelAttribute(
                                "pageTitle",
                                "Thư viện Reactive")
                        .modelAttribute("books", books)
                        .build());
    }
}
```

Controller dùng `@Controller` để bật view resolution. Nó trả `Mono<Rendering>`; model có `Flux` sách. WebFlux resolve `books` thành list trước khi template engine chạy.

Trong ứng dụng thực tế, thay `Flux.just` bằng service/repository reactive. Giữ truy vấn trong service; controller chỉ kết hợp publisher và chọn view. Không gọi `block()` hoặc `subscribe()` thủ công.

### 5.5. home.ftlh

Đặt file tại `src/main/resources/templates/home.ftlh`:

```html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>${pageTitle}</title>
    <link rel="stylesheet" href="/css/site.css">
</head>
<body>
    <main>
        <h1>${pageTitle}</h1>
        <p>Danh sách tài liệu đang có:</p>
        <ul>
            <#list books as book>
                <li>${book.title}</li>
            <#else>
                <li>Chưa có tài liệu.</li>
            </#list>
        </ul>
    </main>
</body>
</html>
```

Hậu tố `.ftlh` dùng HTML output format của FreeMarker và bật auto-escaping theo cấu hình mặc định của định dạng này. Khi template nhận dữ liệu do người dùng nhập, vẫn phải hiểu context escaping và tránh dùng cú pháp tắt escaping trừ khi đã kiểm soát nội dung.

### 5.6. site.css

Đặt file tại `src/main/resources/static/css/site.css`:

```css
body {
    font-family: system-ui, sans-serif;
    margin: 2rem auto;
    max-width: 48rem;
    line-height: 1.6;
    padding: 0 1rem;
}

h1 {
    color: #174a6e;
}

li {
    margin: 0.4rem 0;
}
```

CSS được phục vụ như static resource. Template tham chiếu đường dẫn `/css/site.css`; không cần qua FreeMarker.

## 6. Chạy và kiểm tra ứng dụng mẫu

Từ thư mục chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Mở `http://localhost:8080/` hoặc gọi:

```bash
curl -i http://localhost:8080/
```

Response cần có status 200 và media type `text/html`. Phần body HTML đã render phải chứa nội dung tương tự:

```html
<h1>Thư viện Reactive</h1>
<p>Danh sách tài liệu đang có:</p>
<ul>
    <li>Reactive Streams</li>
    <li>Spring WebFlux</li>
    <li>Reactive Systems</li>
</ul>
```

Đây là đoạn body minh họa; khoảng trắng và cách xuống dòng có thể khác do template renderer. Các giá trị quan trọng phải xuất hiện trong HTML đã render.

## 7. Kiểm thử bằng WebTestClient

Kiểm thử cần đi qua server WebFlux và view resolver để phát hiện lỗi template path, engine, codec và media type. Ví dụ:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HomePageIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void rendersFreeMarkerTemplate() {
        client.get()
                .uri("/")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_HTML)
                .expectBody(String.class)
                .value(html -> {
                    assertThat(html)
                            .contains("<h1>Thư viện Reactive</h1>");
                    assertThat(html)
                            .contains("Reactive Streams");
                    assertThat(html)
                            .contains("Spring WebFlux");
                    assertThat(html)
                            .contains("Reactive Systems");
                });
    }

    @Test
    void staticCssIsServed() {
        client.get()
                .uri("/css/site.css")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith("text/css")
                .expectBody(String.class)
                .value(css ->
                        assertThat(css).contains("font-family"));
    }
}
```

Chạy test:

```bash
mvn test
```

Hai test xác nhận request tới `/` đi qua controller, view resolution và FreeMarker, rồi trả HTML với model đã render; file CSS cũng được phục vụ từ static resource handler của WebFlux.

Đây là integration test qua embedded reactive server. Unit test chỉ gọi controller sẽ không chứng minh template engine và static resource mapping đã được cấu hình đúng.

## 8. Cấu hình FreeMarker thủ công khi không dùng Spring Boot

Trong ứng dụng Spring Framework thuần, cần đăng ký view resolver và configurer:

```java
@Configuration
class FreeMarkerWebFluxConfiguration
        implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(
            ViewResolverRegistry registry) {
        registry.freeMarker();
    }

    @Bean
    FreeMarkerConfigurer freeMarkerConfigurer() {
        FreeMarkerConfigurer configurer =
                new FreeMarkerConfigurer();

        configurer.setTemplateLoaderPath(
                "classpath:/templates/freemarker");

        return configurer;
    }
}
```

Template `welcome` được tìm theo loader path đã khai báo, ví dụ `classpath:/templates/freemarker/welcome.ftl` theo suffix của resolver.

Nếu dùng Spring Boot, starter FreeMarker đã cung cấp auto-configuration cho WebFlux. Không khai báo thêm một resolver thủ công trùng chức năng nếu không cần. Nếu muốn thay đổi cấu hình Boot, hãy kiểm tra bean hiện có và dùng đúng điểm mở rộng; trong Boot, thường chỉ cần cấu hình properties hoặc bean tùy biến.

Nếu bổ sung `WebFluxConfigurer` trong Boot, không gắn `@EnableWebFlux` chỉ để đăng ký view resolver. Annotation đó chuyển ứng dụng sang chế độ tự quản lý hạ tầng WebFlux và làm WebFlux auto-configuration của Boot back off. Chỉ dùng khi thật sự muốn nhận trách nhiệm cấu hình đầy đủ.

## 9. Cấu hình Thymeleaf với WebFlux

Trong Spring Boot, có thể dùng starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-thymeleaf</artifactId>
</dependency>
```

Boot auto-configure tích hợp phù hợp khi ứng dụng đang chạy WebFlux. Template mặc định nằm dưới `src/main/resources/templates`. Ví dụ:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title th:text="${pageTitle}">Trang chủ</title>
</head>
<body>
    <h1 th:text="${pageTitle}">Trang chủ</h1>
    <ul>
        <li th:each="book : ${books}"
            th:text="${book.title}">
            Tên sách
        </li>
    </ul>
</body>
</html>
```

Với Spring Framework 6.x, Thymeleaf cung cấp thư viện Spring integration tương ứng, thường là `thymeleaf-spring6`. Tích hợp reactive dùng `SpringResourceTemplateResolver`, `SpringWebFluxTemplateEngine` và `ThymeleafReactiveViewResolver`. Không dùng `SpringTemplateEngine`/`ThymeleafViewResolver` của MVC thay cho reactive integration.

Nếu tự cấu hình thủ công, cần tạo template resolver, reactive template engine và reactive view resolver theo tài liệu Thymeleaf cho phiên bản đang dùng. Tránh tự khai báo các bean đó khi Boot đã auto-configure cùng chức năng.

## 10. Cấu hình Mustache với WebFlux

Trong Spring Boot, thêm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mustache</artifactId>
</dependency>
```

Template mặc định được tìm trong `src/main/resources/templates`. Một file `home.mustache` có thể chứa:

```html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>{{pageTitle}}</title>
</head>
<body>
    <h1>{{pageTitle}}</h1>
    <ul>
        {{#books}}
            <li>{{title}}</li>
        {{/books}}
    </ul>
</body>
</html>
```

Controller chuẩn bị model có key `pageTitle` và `books`. Mustache phù hợp khi muốn template ít logic; xử lý lọc, phân trang và tính toán trong Java service. Với cấu hình Boot, kiểm tra các thuộc tính `spring.mustache.*` nếu cần thay prefix, suffix hoặc caching.

## 11. WebFlux.fn cũng có thể render template

Ngoài annotated controller, WebFlux hỗ trợ functional endpoint. `ServerResponse.BodyBuilder` có phương thức `render` để trả view name cùng model:

```java
@Bean
RouterFunction<ServerResponse> pageRoutes() {
    return RouterFunctions.route(
            GET("/welcome"),
            request -> ServerResponse.ok()
                    .render(
                            "home",
                            Map.of(
                                    "pageTitle",
                                    "Trang chào mừng",
                                    "books",
                                    List.of(
                                            Map.of("title", "WebFlux"),
                                            Map.of("title", "Reactor")))));
}
```

Đây là snippet cần các static import và bean configuration. View resolver và template engine vẫn là các bean của cùng Spring WebFlux application context. Khác biệt nằm ở cách route và handler được khai báo; không phải một cơ chế template riêng.

Không trộn handler functional với annotated controller chỉ vì muốn dùng một template engine khác. Chọn programming model theo cấu trúc ứng dụng, còn view technology có thể được dùng chung nếu resolver tương ứng đã đăng ký.

## 12. Dùng view cho HTML và HttpMessageWriterView cho JSON/XML

Template engine thường render HTML. Nếu một model cần biểu diễn bằng JSON hoặc XML, WebFlux có `HttpMessageWriterView`, dùng codec/`HttpMessageWriter` để ghi model theo media type.

Ví dụ cấu hình default view JSON:

```java
@Configuration
class ViewNegotiationConfiguration
        implements WebFluxConfigurer {

    @Override
    public void configureViewResolvers(
            ViewResolverRegistry registry) {

        registry.freeMarker();

        Jackson2JsonEncoder encoder =
                new Jackson2JsonEncoder();

        registry.defaultViews(
                new HttpMessageWriterView(encoder));
    }
}
```

Đây là cấu hình Framework cần các import và Jackson codec phù hợp. View default được chọn khi media type request phù hợp. Với API công khai, thường dễ hiểu hơn nếu dùng endpoint `@RestController` riêng cho JSON và endpoint `@Controller` riêng cho HTML.

Không trả DTO từ `@RestController` rồi kỳ vọng FreeMarker render nó. `@ResponseBody` yêu cầu ghi response bằng message writer; view resolution là một đường xử lý khác.

## 13. Static resources, WebJars và welcome page

Boot WebFlux phục vụ static resource từ classpath. Các vị trí mặc định thường gặp:

- `classpath:/static/`
- `classpath:/public/`
- `classpath:/resources/`
- `classpath:/META-INF/resources/`

Nếu có `index.html` trong static locations, Boot có thể dùng làm welcome page. Nếu không tìm thấy static index, Boot kiểm tra template tên `index`. Welcome page là fallback; route ứng dụng đã khai báo có thể được ưu tiên theo thứ tự HandlerMapping.

WebJars đóng gói thư viện frontend trong JAR. WebFlux có thể phục vụ tài nguyên WebJars dưới `/webjars/**`. Không cần copy thủ công file thư viện vào static folder nếu đã dùng artifact WebJar và mapping phù hợp.

Khi frontend build ra bundle, có thể đặt bundle trong `src/main/resources/static`. Với deployment CDN hoặc frontend server riêng, cấu hình CORS, CSP và cookie domain theo origin thực tế. Không dùng template engine chỉ để nhúng từng file JS/CSS tĩnh.

## 14. Form, validation và dữ liệu trong template

Template có thể hiển thị dữ liệu form, lỗi validation và thông báo quốc tế hóa. Luồng thường gặp:

1. Controller nhận form request và bind dữ liệu vào command object.
2. Bean Validation kiểm tra dữ liệu đầu vào.
3. Service xử lý nghiệp vụ.
4. Controller đưa dữ liệu hoặc lỗi vào model.
5. View resolver render template với model đã hoàn tất.

Với FreeMarker, Spring cung cấp các macro hỗ trợ binding và hiển thị lỗi form trong `spring.ftl`. Với Thymeleaf, các thuộc tính như `th:field`, `th:errors` và `th:errorclass` hỗ trợ tích hợp form. Khả năng và cú pháp chi tiết phụ thuộc template engine.

Đối với WebFlux, các publisher reactive có thể nằm trong model. Nếu một form cần dữ liệu tham chiếu, compose service publisher rồi đưa kết quả vào model; không gọi `block()` để chờ dữ liệu.

Các lưu ý bảo mật:

- Không đưa entity đầy đủ có password, token hoặc trường nội bộ vào model. Dùng view DTO chỉ chứa dữ liệu cần hiển thị.
- Bảo vệ POST form bằng CSRF khi dùng Spring Security.
- Escape dữ liệu theo context HTML, attribute, URL hoặc JavaScript.
- Không render chuỗi do người dùng nhập như template source.
- Giới hạn quyền truy cập template; template có thể truy cập bean trong application context.
- Không cho phép người dùng bên ngoài chỉnh sửa template trên server trừ khi có sandbox và threat model phù hợp.

## 15. Redirect, lỗi và trang lỗi HTML

Controller có thể trả redirect view:

```java
@GetMapping("/old-home")
public Rendering redirect() {
    return Rendering.redirectTo("/").build();
}
```

Hoặc trả logical view name có prefix `redirect:` nếu resolver hỗ trợ. Redirect không phải là render một template mới; server gửi response redirect và browser thực hiện request tiếp theo.

Spring Boot WebFlux có error handler mặc định. Có thể cung cấp template lỗi HTML theo quy ước dưới thư mục `templates/error`, ví dụ `error/404.ftlh` hoặc `error/5xx.ftlh` khi dùng FreeMarker. Static error page có thể đặt trong `public/error`. Kiểm tra quy ước và đường dẫn cụ thể theo Boot version.

Đối với API machine-to-machine, trả Problem Details hoặc JSON error response rõ ràng; đừng trả một trang HTML lỗi cho endpoint được công bố là JSON. Có thể phân tách browser route và API route theo path hoặc content negotiation.

Không để stack trace, SQL, token, đường dẫn nội bộ hoặc dữ liệu nhạy cảm xuất hiện trong template lỗi production. Ghi log chi tiết ở server và hiển thị thông báo an toàn cho người dùng.

## 16. Reactive rendering và giới hạn tài nguyên

View engine tạo HTML trước khi server gửi response. Mặc dù controller/service có thể reactive, bước render template vẫn cần thực hiện công việc xử lý nội dung. Một số nguyên tắc:

- Không gọi JDBC/JPA blocking trực tiếp trên event-loop để chuẩn bị model.
- Dùng R2DBC hoặc client reactive khi phù hợp; nếu phải dùng thư viện blocking, chuyển công việc sang scheduler phù hợp trước khi render.
- Không đưa một `Flux` vô hạn vào model vì WebFlux collect multi-value publisher trước khi render.
- Phân trang danh sách dài; giới hạn số bản ghi đưa vào một trang.
- Không render toàn bộ file lớn thành một chuỗi HTML.
- Cache template đã biên dịch trong production nếu engine hỗ trợ.
- Tránh khởi tạo engine hoặc resolver mới cho từng request.
- Giữ template và model đơn giản để giảm CPU và memory pressure.

Nếu cần cập nhật giao diện liên tục, dùng SSE/WebSocket hoặc một endpoint streaming riêng. Template rendering phù hợp với một response HTML hoàn chỉnh hoặc một fragment hữu hạn; nó không thay thế cơ chế truyền sự kiện.

## 17. Chọn công nghệ theo yêu cầu

| Nhu cầu | Lựa chọn phù hợp | Điểm cần lưu ý |
|---|---|---|
| Website server-rendered truyền thống | Thymeleaf hoặc FreeMarker | Tích hợp form, layout và model |
| Template logic nhẹ | Mustache | Chuẩn bị model ở service/controller |
| Email hoặc text template | FreeMarker | Có thể dùng engine ngoài HTTP view |
| SPA frontend độc lập | Static assets + WebFlux JSON API | CORS/authentication và frontend routing |
| Trang tĩnh đơn giản | `index.html` trong static resources | Không cần template engine |
| HTML/XML/JSON từ một model theo media type | View resolver + `HttpMessageWriterView` | Cấu hình content negotiation rõ ràng |
| Template engine đặc thù | Custom `ViewResolver` hoặc `ScriptTemplateConfigurer` | Cần quản lý concurrency và lifecycle |
| JSP/JSTL hiện hữu | Spring MVC | JSP thuộc Servlet stack, không phải WebFlux |

Không có một template engine tốt nhất cho mọi dự án. Chọn theo yêu cầu layout, form, logic template, kinh nghiệm nhóm, khả năng tương thích version và cách deploy frontend.

## 18. Những lỗi thường gặp

1. **Dùng `@RestController` rồi trả tên template.** Chuỗi được ghi vào response body; dùng `@Controller` hoặc `Rendering`.
2. **Dùng nhầm `ThymeleafViewResolver` của MVC.** WebFlux cần `ThymeleafReactiveViewResolver` và `SpringWebFluxTemplateEngine`.
3. **Chỉ thêm thư viện engine nhưng thiếu view resolver.** Kiểm tra auto-configuration của Boot hoặc đăng ký resolver thủ công.
4. **Đặt template sai thư mục.** Với Boot mặc định, dùng `src/main/resources/templates`; nếu đổi loader path, cập nhật cấu hình đồng bộ.
5. **Dùng JSP với WebFlux.** JSP cần Servlet API; chuyển sang Thymeleaf/FreeMarker/Mustache hoặc dùng Spring MVC.
6. **Gọi `block()` trong controller để lấy model.** Việc này chặn event-loop; trả `Mono`/`Flux` và để WebFlux resolve model.
7. **Đưa Flux vô hạn vào template model.** View renderer phải thu thập danh sách; dùng SSE/WebSocket cho stream liên tục.
8. **Collect toàn bộ dữ liệu lớn.** Phân trang và giới hạn kết quả trước khi render.
9. **Không phân biệt logical view name và file path.** Controller trả tên view; resolver ghép prefix/suffix và tìm file.
10. **Dùng `@ResponseBody` khi muốn render view.** Annotation này chuyển kết quả sang message writer.
11. **Cấu hình hai view resolver cùng xử lý một tên.** Đặt order, view name pattern và prefix/suffix rõ ràng.
12. **Đăng ký resolver thủ công trong khi Boot đã auto-configure.** Có thể tạo resolver trùng hoặc cấu hình xung đột; chọn một chủ sở hữu.
13. **Cho rằng mọi tính năng FreeMarker hoạt động giống MVC.** Boot cảnh báo một số tính năng không được hỗ trợ với WebFlux; kiểm tra feature cụ thể.
14. **Dùng Thymeleaf MVC integration trong WebFlux.** Chọn đúng artifact và reactive resolver theo version Spring.
15. **Đưa entity hoặc secret vào model.** Tạo view DTO và chỉ expose field cần thiết.
16. **Tắt auto-escaping để sửa HTML hiển thị sai.** Xử lý escaping theo context thay vì đưa XSS vào template.
17. **Cho người dùng sửa template trên server.** Template có thể truy cập bean context; giữ template trong trust boundary.
18. **Dùng static resource path quá rộng.** Kiểm tra mapping để asset không che endpoint API.
19. **Nhầm static resource với template.** Static file được phục vụ nguyên trạng; template cần controller/view resolver.
20. **Không test HTTP response thật.** Kiểm tra status, Content-Type, rendered body và static assets bằng WebTestClient.
21. **Dùng template engine để trả JSON API.** Dùng message codec hoặc `@RestController`; chỉ dùng `HttpMessageWriterView` khi có lý do content negotiation.
22. **Render lỗi với stack trace.** Dùng thông báo an toàn và log nội bộ.
23. **Không bật CSRF protection cho form.** Kiểm tra cấu hình Spring Security và token trong form.
24. **Chạy ứng dụng với cả starter MVC và WebFlux nhưng tưởng server chắc chắn reactive.** Boot thường ưu tiên MVC khi cả hai starter cùng có mặt; kiểm tra application type.
25. **Dùng ví dụ cấu hình từ version khác.** API view resolver, template integration và Boot property có thể thay đổi; dùng tài liệu khớp version dependency.

## 19. Checklist cấu hình production

Trước khi phát hành giao diện WebFlux, hãy kiểm tra:

- Ứng dụng thực sự chạy WebFlux hay Spring MVC?
- Giao diện là static SPA, server-side template hay mô hình hybrid?
- Template engine có hỗ trợ WebFlux và version Spring hiện tại không?
- Đã thêm đúng starter/dependency chưa?
- `@Controller` và `@RestController` có được dùng đúng ngữ nghĩa?
- View name, resolver, prefix/suffix và template path có khớp?
- Model có chứa publisher reactive không? Có publisher vô hạn hoặc danh sách quá lớn không?
- Có gọi blocking API trên event-loop trong lúc chuẩn bị model không?
- HTML output có auto-escaping và xử lý XSS đúng không?
- Template có nằm trong trust boundary? Model có lộ secret/entity nội bộ không?
- Form có validation và CSRF protection?
- Static resource, WebJars và welcome page có mapping đúng?
- Error page có an toàn và phù hợp browser/API?
- Có integration test qua embedded WebFlux server và WebTestClient?
- Có test riêng cho template not found, empty model, lỗi service và static resource?
- Cache template, memory, response size và latency có được quan sát trong production?

**Ghi nhớ:** WebFlux hỗ trợ dynamic HTML bằng view resolution. Controller trả logical view name hoặc `Rendering`, model chứa dữ liệu, `ViewResolver` chọn engine và template được render thành HTTP response. Spring Boot hỗ trợ FreeMarker, Thymeleaf và Mustache; Spring Framework còn có FreeMarker integration, script view và custom resolver. Dữ liệu reactive có thể nằm trong model nhưng `Flux` được collect thành list trước khi render. Static SPA assets được phục vụ qua resource handler, còn JSP thuộc Servlet stack. Chọn đúng engine, starter, resolver và lifecycle; kiểm tra escaping, model security, pagination và test response thực tế.

## Tài liệu tham khảo

- Spring Boot 3.5 — [Reactive Web Applications: static resources, template engines and WebFlux support](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html).
- Spring Framework 6.2 — [View Technologies in WebFlux: Thymeleaf, FreeMarker and script views](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-view.html).
- Spring Framework 6.2 — [DispatcherHandler and WebFlux view resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html).
- Spring Framework 6.2 — [WebFlux Config: ViewResolverRegistry and FreeMarker configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html).
- Thymeleaf — [Thymeleaf + Spring integration](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html).
- Spring Framework — [Rendering Javadoc for WebFlux](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/result/view/Rendering.html).
- Spring Framework — [ServerResponse.BodyBuilder Javadoc: functional view rendering](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.BodyBuilder.html).

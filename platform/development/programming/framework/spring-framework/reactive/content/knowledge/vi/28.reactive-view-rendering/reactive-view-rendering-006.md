# Giới hạn công nghệ view chặn và khác biệt với JSP trên Servlet

## 1. View resolution trong Spring WebFlux

Spring WebFlux có thể render HTML phía server bên cạnh việc cung cấp REST API. Controller trả về tên view và model; framework tìm template tương ứng, render nội dung rồi ghi vào HTTP response.

Các thành phần chính:

- `ViewResolver` ánh xạ tên view logic, ví dụ `greeting`, thành một `View`.
- `View` nhận model, media type và exchange để render.
- `ViewResolutionResultHandler` điều phối view resolution trong `DispatcherHandler`.
- `ServerWebExchange` cung cấp request, response và context của HTTP exchange.

~~~text
HTTP Request
     |
     v
DispatcherHandler
     |
     v
HandlerMapping -> @Controller
     |
     v
HandlerResult + Model
     |
     v
ViewResolutionResultHandler
     |
     v
ViewResolver -> View
     |
     v
Template engine + Model
     |
     v
ServerHttpResponse
~~~

Hợp đồng render của WebFlux là reactive:

~~~java
Mono<Void> render(
    Map<String, ?> model,
    MediaType contentType,
    ServerWebExchange exchange
);
~~~

`Mono<Void>` biểu diễn thời điểm render hoàn tất hoặc phát lỗi. Tuy nhiên, kiểu trả về Publisher không tự biến mọi thao tác bên trong template engine thành non-blocking. Implementation của view và custom helper quyết định thread thực thi thực tế.

### 1.1. Controller trả về tên view

Dùng `@Controller` khi muốn Spring xử lý kết quả như tên template:

~~~java
@Controller
public class GreetingPageController {

    @GetMapping("/greeting")
    public String greeting(Model model) {
        model.addAttribute("message", "Xin chào WebFlux");
        return "greeting";
    }
}
~~~

Nếu dùng `@RestController` hoặc `@ResponseBody`, chuỗi trả về thường được ghi trực tiếp vào response body thay vì được hiểu là tên view.

Controller cũng có thể trả `Mono<String>`:

~~~java
@GetMapping("/greeting")
public Mono<String> greeting(Model model) {
    model.addAttribute("message", "Xin chào WebFlux");
    return Mono.just("greeting");
}
~~~

### 1.2. Reactive data trong model

WebFlux hỗ trợ model attribute có kiểu Publisher:

~~~java
model.addAttribute("profile", profileService.findProfile(userId));
return Mono.just("profile");
~~~

Trước khi render, `AbstractView` resolve các model attribute bất đồng bộ:

- `Mono<T>` thành một giá trị hoặc rỗng nếu Mono không phát item.
- `Flux<T>` được thu thập thành `List<T>`.
- Publisher khác được chuyển đổi nếu có adapter phù hợp.

Một `Flux` vô hạn không phù hợp với model template thông thường vì việc collect List sẽ chờ nguồn complete và có thể giữ dữ liệu tăng không giới hạn. Nếu cần stream HTML, hãy dùng HTML fragments hoặc giao thức streaming.

### 1.3. Content negotiation

`ViewResolutionResultHandler` có thể chọn view theo media type client yêu cầu. WebFlux cung cấp `HttpMessageWriterView` để render model qua codec, chẳng hạn JSON hoặc XML. Không cần dùng template engine để tạo JSON khi codec đã đáp ứng.

## 2. Blocking và tác động tới event loop

### 2.1. Vì sao blocking nguy hiểm?

WebFlux thường chạy trên một số lượng nhỏ event-loop worker thread cố định. Mỗi worker có thể phục vụ nhiều request bằng I/O bất đồng bộ và callback.

Nếu callback gọi thư viện đồng bộ rồi chờ kết quả, worker hiện tại không xử lý được các sự kiện khác trong thời gian đó. Khi nhiều request cùng block:

- Request khác phải chờ event loop được giải phóng.
- Độ trễ tăng dù CPU có thể chưa sử dụng hết.
- Khả năng phục vụ đồng thời giảm.
- Template helper đọc file, gọi JDBC hoặc gọi HTTP đồng bộ có thể làm nghẽn luồng xử lý.

Spring MVC trên Servlet giả định request có thể block và dùng thread pool để hấp thụ thời gian chờ. WebFlux giả định phần xử lý chính là non-blocking, vì vậy blocking I/O có tác động lớn hơn tới concurrency.

### 2.2. Phân biệt I/O-bound và CPU-bound

| Công việc | Đặc điểm | Hướng xử lý |
| --- | --- | --- |
| Đọc file bằng API đồng bộ | I/O blocking | boundedElastic hoặc executor riêng |
| JDBC/JPA đồng bộ | I/O blocking | Cô lập; cân nhắc R2DBC nếu cần reactive end-to-end |
| Gọi HTTP bằng WebClient | I/O non-blocking | Kết hợp trực tiếp trong reactive chain |
| Tính toán CPU nặng | CPU-bound | Scheduler CPU phù hợp hoặc tối ưu thuật toán |
| Render template trong memory | Thường là CPU và xử lý đồng bộ | Đo thời gian, kiểm soát output và scheduler |

### 2.3. Cô lập API blocking

Nếu phải gọi thư viện đồng bộ, tạo Publisher từ callable và chuyển subscription sang boundedElastic:

~~~java
Mono<LegacyReport> report =
    Mono.fromCallable(() -> legacyReportClient.load(reportId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`subscribeOn` chuyển quá trình subscribe và thực thi callable sang scheduler chỉ định.

Đừng nhầm với:

~~~java
Mono.fromCallable(() -> legacyReportClient.load(reportId))
    .publishOn(Schedulers.boundedElastic());
~~~

`publishOn` chuyển các operator phía sau nó. Callable nguồn có thể đã chạy trước khi tín hiệu tới publishOn. Dùng subscribeOn để cô lập chính source blocking.

Không gọi `block()`, `Future.get()` hoặc `Thread.sleep()` trực tiếp trong controller, view hay event-loop callback. Không tạo thread mới cho từng request.

### 2.4. Không phải mọi view engine đều blocking

Một view có thể trả `Mono<Void>` nhưng vẫn thực hiện công việc đồng bộ bên trong. Ngược lại, một số tích hợp WebFlux đã chủ động cô lập các bước blocking.

Ví dụ, `FreeMarkerView` từ Spring Framework 6.1 sử dụng boundedElastic cho template lookup có thể blocking. Tuy vậy, custom directive, macro, helper hoặc lời gọi dịch vụ riêng vẫn cần được đánh giá độc lập.

## 3. Công nghệ view được hỗ trợ và giới hạn

### 3.1. Thymeleaf

Tích hợp Thymeleaf với WebFlux do dự án Thymeleaf quản lý. Các thành phần chính:

- `SpringResourceTemplateResolver` tìm template.
- `SpringWebFluxTemplateEngine` xử lý template.
- `ThymeleafReactiveViewResolver` kết nối engine với view resolution.

Spring Boot có auto-configuration cho Thymeleaf. Template mặc định nằm trong `src/main/resources/templates`.

Có thể cấu hình reactive chunked mode:

~~~properties
spring.thymeleaf.reactive.max-chunk-size=8KB
spring.thymeleaf.reactive.chunked-mode-view-names=reports/**
~~~

`max-chunk-size` giới hạn kích thước DataBuffer khi ghi response. Khi được cấu hình, các view phù hợp có thể render theo CHUNKED mode. `full-mode-view-names` có thể chỉ định view cần FULL mode.

### 3.2. FreeMarker

Spring Framework có tích hợp FreeMarker trực tiếp cho WebFlux qua `FreeMarkerConfigurer`, `FreeMarkerViewResolver` và `FreeMarkerView`. Spring Boot cũng có auto-configuration; template mặc định được tìm trong `classpath:/templates/` và suffix mặc định là `.ftlh`.

`.ftlh` là định dạng HTML của FreeMarker có auto-escaping theo output format.

Một số property FreeMarker của Boot chỉ hỗ trợ Spring MVC, ví dụ:

- `spring.freemarker.allow-request-override`.
- `spring.freemarker.allow-session-override`.
- `spring.freemarker.expose-request-attributes`.
- `spring.freemarker.expose-session-attributes`.
- `spring.freemarker.expose-spring-macro-helpers`.
- `spring.freemarker.cache`.
- `spring.freemarker.content-type`.

Các property gắn với `HttpServletRequest`, `HttpSession` hoặc Servlet view không thể áp dụng nguyên trạng cho reactive exchange. Khi chuyển từ MVC, kiểm tra metadata của đúng phiên bản Boot thay vì sao chép toàn bộ cấu hình.

Một giới hạn khác là output buffering: implementation `FreeMarkerView` của Spring Framework 6.2 xử lý template thành buffer trong bộ nhớ trước khi ghi response. Trang rất lớn có thể cần memory tương ứng với toàn bộ HTML đã render; view thông thường không phải stream vô hạn. Nếu cần output theo từng phần, cân nhắc Thymeleaf chunked mode hoặc HTML fragments.

### 3.3. Mustache và script templates

Spring Boot có auto-configuration cho Mustache trong WebFlux. Template mặc định nằm trong `src/main/resources/templates` và dùng suffix `.mustache`. Mustache phù hợp với template đơn giản, ít logic và ít helper.

Spring Framework cũng có script view cho thư viện chạy trên JSR-223. Engine cần triển khai `ScriptEngine` và `Invocable`; có thể cấu hình bằng `ScriptTemplateConfigurer`:

~~~java
@Override
public void configureViewResolvers(ViewResolverRegistry registry) {
    registry.scriptTemplate();
}
~~~

Thread-safety, chi phí biên dịch và hành vi blocking phụ thuộc script engine. Một engine không thread-safe có thể cần instance riêng hoặc cơ chế đồng bộ phù hợp.

### 3.4. JSP trên Servlet khác WebFlux thế nào?

Spring Framework tích hợp JSP/JSTL với Spring MVC. Resolver thường dùng là `InternalResourceViewResolver`; khi dùng JSTL, Spring MVC dùng `JstlView` để chuẩn bị i18n và form binding.

| Spring MVC + JSP | Spring WebFlux |
| --- | --- |
| `DispatcherServlet` | `DispatcherHandler` |
| `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange` |
| `InternalResourceViewResolver` | WebFlux `ViewResolver` |
| `JstlView` / JSP servlet | Thymeleaf reactive, FreeMarker WebFlux, Mustache hoặc custom reactive View |
| Servlet request/response lifecycle | Publisher và `Mono<Void>` |
| Thread pool Servlet hấp thụ blocking | Event loop cần tránh blocking |

JSP được biên dịch và thực thi qua JSP engine/Servlet container. `InternalResourceViewResolver` dispatch tới Servlet resource; Spring form tags và JSTL dựa trên servlet request, page context và Spring MVC.

Resolver JSP thuộc module `spring-webmvc`. Nó không phải WebFlux `ViewResolver` và không nhận `ServerWebExchange` để render. Chỉ thêm JSP file hoặc JSP engine vào ứng dụng WebFlux không làm JSP trở thành view native của WebFlux.

### 3.5. Chạy WebFlux trên Tomcat có làm JSP hoạt động không?

Không. Tomcat và Jetty có thể chạy cả Spring MVC lẫn WebFlux, nhưng hai framework sử dụng container theo cách khác nhau:

- MVC dùng Servlet blocking I/O và cho phép ứng dụng truy cập Servlet API trực tiếp.
- WebFlux dùng non-blocking I/O của server; nếu chạy trên Servlet container, Servlet API nằm phía sau adapter và không được expose trực tiếp cho application code.

Chọn Tomcat làm reactive server không đồng nghĩa ứng dụng đang chạy Spring MVC hoặc có JSP resolver. WebFlux cũng không phụ thuộc bắt buộc vào Servlet API và không dùng `src/main/webapp` như ứng dụng WAR truyền thống.

## 4. Streaming HTML và giới hạn model

### 4.1. Flux trong model không tự tạo stream

~~~java
model.addAttribute("orders", orderService.findAll());
return Mono.just("orders");
~~~

Nếu `findAll()` trả `Flux<Order>`, view resolution thu thập Flux thành `List<Order>` trước khi render. Cách này phù hợp với danh sách hữu hạn và vừa bộ nhớ.

Không dùng cách trên cho Flux vô hạn, event stream liên tục hoặc dataset rất lớn. Hãy phân trang, giới hạn số item hoặc dùng giao thức streaming.

### 4.2. HTML fragments

Spring Framework 6.2 hỗ trợ render nhiều HTML fragment trong một request. Controller có thể trả `Collection<Fragment>` hoặc `FragmentsRendering`:

~~~java
@GetMapping("/dashboard")
public FragmentsRendering dashboard() {
    return FragmentsRendering.fragment("summary")
        .fragment("notifications")
        .build();
}
~~~

Nếu cần stream fragment, có thể tạo `FragmentsRendering` từ `Flux<Fragment>` hoặc trả `Flux<Fragment>` trực tiếp. Đây là cách phù hợp với HTMX/Hotwire Turbo và HTML-over-the-wire.

### 4.3. Redirect, forward và static resources

WebFlux hỗ trợ redirect bằng prefix `redirect:` hoặc `Rendering.redirectTo`. WebFlux không hỗ trợ Servlet-style `forward:` dispatch.

WebFlux có ResourceHandler và ResourceResolver để phục vụ static assets. Tuy nhiên, hiện không có transparent URL rewriting cho static resource chain giống Spring MVC. Khi cần versioned URL, có thể dùng `ResourceUrlProvider` trực tiếp hoặc helper riêng; tránh block event loop chỉ để rewrite URL.

### 4.4. Memory và bảo mật template

Template rendering có thể giữ model và output trong bộ nhớ. Hãy chỉ đưa field cần thiết vào model, không gọi database hoặc dịch vụ từ expression trong template, không collect Flux lớn thành List và đo allocation/GC dưới tải.

Template view có thể truy cập bean trong application context. Không cho người dùng cuối hoặc nguồn bên ngoài tùy ý sửa template được render trong trust boundary. Giữ template trong nguồn đã kiểm soát, escape dữ liệu HTML và không expose bean có quyền cao nếu không cần.

## 5. Ví dụ Spring Boot 3.5.7 + Java 17 hoàn chỉnh

Ví dụ dùng FreeMarker để render trang greeting. Model chứa `Mono<Greeting>`, controller trả `Mono<String>` làm view name. Spring Boot tự cấu hình WebFlux và FreeMarker.

### 5.1. Cấu trúc project

~~~text
webflux-view-demo/
├── pom.xml
├── src/main/resources/
│   ├── application.properties
│   └── templates/
│       └── greeting.ftlh
├── src/main/java/example/view/
│   ├── WebFluxViewApplication.java
│   ├── Greeting.java
│   ├── GreetingService.java
│   └── GreetingPageController.java
└── src/test/java/example/view/
    └── GreetingPageControllerTest.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-view-demo</artifactId>
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
~~~

### 5.3. application.properties

~~~properties
server.port=8080
spring.freemarker.template-loader-path=classpath:/templates/
spring.freemarker.suffix=.ftlh
spring.freemarker.charset=UTF-8
~~~

### 5.4. WebFluxViewApplication.java

~~~java
package example.view;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxViewApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxViewApplication.class, args);
    }
}
~~~

### 5.5. Greeting.java

~~~java
package example.view;

public record Greeting(
    String message,
    String generatedAt
) {
}
~~~

### 5.6. GreetingService.java

~~~java
package example.view;

import java.time.Instant;
import java.time.Duration;
import java.time.format.DateTimeFormatter;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class GreetingService {

    public Mono<Greeting> loadGreeting() {
        return Mono.delay(Duration.ofMillis(20))
            .map(ignored -> new Greeting(
                "Xin chào từ Spring WebFlux",
                DateTimeFormatter.ISO_INSTANT.format(Instant.now())
            ));
    }
}
~~~

`Mono.delay` minh họa nguồn dữ liệu bất đồng bộ. Trong ứng dụng thật, service có thể gọi reactive repository, WebClient hoặc Publisher khác.

### 5.7. GreetingPageController.java

~~~java
package example.view;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

import reactor.core.publisher.Mono;

@Controller
@RequestMapping("/pages")
public class GreetingPageController {

    private final GreetingService greetingService;

    public GreetingPageController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public Mono<String> greeting(Model model) {
        model.addAttribute("greeting", greetingService.loadGreeting());
        return Mono.just("greeting");
    }
}
~~~

Controller thêm `Mono<Greeting>` vào model và trả view name `greeting`. WebFlux resolve model Publisher trước khi render. Không gọi `block()` để lấy Greeting.

### 5.8. greeting.ftlh

~~~html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>WebFlux View Demo</title>
</head>
<body>
    <main>
        <h1>${greeting.message}</h1>
        <p>Thời điểm tạo: <time>${greeting.generatedAt}</time></p>
    </main>
</body>
</html>
~~~

Đuôi `.ftlh` dùng HTML output format của FreeMarker, hỗ trợ auto-escaping cho dữ liệu được chèn vào template.

### 5.9. GreetingPageControllerTest.java

~~~java
package example.view;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class GreetingPageControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void rendersFreeMarkerViewFromReactiveModel() {
        client.get()
            .uri("/pages/greeting")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_HTML)
            .expectBody(String.class)
            .value(html -> {
                assertTrue(html.contains("Xin chào từ Spring WebFlux"));
                assertTrue(html.contains("<time>"));
            });
    }
}
~~~

Test đi qua HTTP server nhúng và view resolution thật. Nó xác minh status, media type và HTML được render từ reactive model.

### 5.10. Chạy ứng dụng và test

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Gọi endpoint:

~~~bash
curl -i http://localhost:8080/pages/greeting
~~~

Response body có dạng:

~~~html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>WebFlux View Demo</title>
</head>
<body>
    <main>
        <h1>Xin chào từ Spring WebFlux</h1>
        <p>Thời điểm tạo: 2026-11-08T04:00:00Z</p>
    </main>
</body>
</html>
~~~

Giá trị thời gian thực tế được tạo lúc request chạy nên sẽ thay đổi. Đoạn trên chỉ minh họa cấu trúc HTML.

Chạy integration test:

~~~bash
mvn test
~~~

## 6. Kiểm tra, lỗi phổ biến và checklist

### 6.1. Chẩn đoán view resolution

Khi controller trả HTML sai hoặc tên view xuất hiện thành plain text, kiểm tra:

1. Controller có dùng `@Controller` thay vì `@RestController` không?
2. Method có `@ResponseBody` khiến chuỗi được ghi thẳng vào body không?
3. ViewResolver phù hợp có trên classpath không?
4. Template có nằm đúng loader path không?
5. Tên view và suffix có khớp không?
6. Response có đúng Content-Type không?
7. Có nhiều resolver cùng match một view name không?

Nếu API chậm khi render, ghi nhận thread name ở controller/service/helper, tách thời gian lấy dữ liệu khỏi thời gian render, kiểm tra JDBC/JPA/file I/O/HTTP đồng bộ và đo latency dưới tải. Nếu memory tăng, đo model và output, kiểm tra engine có aggregate toàn HTML hay render theo chunk, tránh collect Flux lớn thành List và kiểm tra cancellation.

### 6.2. Lỗi phổ biến

**Lỗi 1 — Dùng @RestController rồi trả tên template.** Chuỗi bị ghi thành response body. Dùng @Controller khi cần view resolution.

**Lỗi 2 — Nghĩ JSP tự hoạt động vì server là Tomcat.** WebFlux trên Tomcat vẫn dùng reactive adapter. JSP resolver thuộc Spring MVC Servlet stack.

**Lỗi 3 — Thêm InternalResourceViewResolver vào WebFlux.** Resolver đó dispatch tới Servlet resource và không phải WebFlux ViewResolver.

**Lỗi 4 — Chỉ nhìn Mono<Void> rồi kết luận render non-blocking.** View implementation có thể gọi API đồng bộ. Kiểm tra engine, helper và thread thực thi.

**Lỗi 5 — Gọi JDBC/JPA hoặc đọc file đồng bộ trong template expression.** Render có thể block event loop. Lấy dữ liệu trong service và cô lập API blocking trước khi đưa vào model.

**Lỗi 6 — Dùng publishOn sau callable để chuyển blocking source.** Callable có thể đã chạy trước publishOn. Dùng fromCallable kết hợp subscribeOn.

**Lỗi 7 — Đưa Flux vô hạn vào model.** View resolution collect Flux thành List và chờ complete. Dùng Fragment rendering hoặc streaming protocol.

**Lỗi 8 — Nghĩ FreeMarker luôn stream HTML từng dòng.** FreeMarkerView có thể aggregate output trước khi ghi. Kiểm tra memory và chọn cách render phù hợp.

**Lỗi 9 — Sao chép mọi property FreeMarker từ MVC sang WebFlux.** Một số property chỉ hỗ trợ Servlet stack. Kiểm tra application properties của đúng phiên bản.

**Lỗi 10 — Dùng JSTL hoặc Spring JSP form tags trong WebFlux.** Các tag này phụ thuộc JSP/Servlet. Chuyển sang form binding của engine reactive hoặc dùng MVC.

**Lỗi 11 — Không cấu hình suffix/template path.** Resolver tìm sai file. Kiểm tra tên view, loader path và suffix.

**Lỗi 12 — Template không auto-escape dữ liệu HTML.** Dữ liệu người dùng có thể tạo XSS. Dùng output format có auto-escaping.

**Lỗi 13 — Cho phép người ngoài chỉnh sửa template.** Template có thể truy cập bean trong application context. Giữ template trong trust boundary.

**Lỗi 14 — Dùng view engine cho JSON API.** Template không phải codec. Dùng ResponseBody và HttpMessageWriter cho JSON/XML.

**Lỗi 15 — Mong đợi forward: như Servlet.** WebFlux không hỗ trợ forward dispatch. Dùng route, controller hoặc redirect.

**Lỗi 16 — Bật cả starter-web và starter-webflux nhưng kỳ vọng Boot chạy WebFlux.** Boot mặc định chọn MVC khi cả hai cùng có. Xác định application type.

**Lỗi 17 — Không kiểm tra cancellation.** Client có thể đóng kết nối giữa lúc render. Custom view và nguồn dữ liệu phải dừng khi subscription bị cancel.

**Lỗi 18 — Chỉ đo controller latency.** Tổng thời gian còn gồm model resolution, template lookup, processing và response write. Đo riêng từng giai đoạn.

### 6.3. Checklist lựa chọn công nghệ view

1. Ứng dụng cần render HTML hay chỉ cung cấp JSON API?
2. Có cần giữ JSP/JSTL hoặc Spring MVC form tags không?
3. Template engine có tích hợp WebFlux chính thức không?
4. View có dùng blocking API hoặc custom helper đồng bộ không?
5. Engine có offload phần blocking hay ứng dụng phải tự làm?
6. Template có aggregate toàn output trong memory không?
7. Có cần chunked rendering hoặc HTML fragments không?
8. Model có Publisher vô hạn hoặc danh sách lớn không?
9. FreeMarker properties nào chỉ hỗ trợ MVC?
10. Có cần content negotiation HTML/JSON không?
11. Template có auto-escaping và nằm trong trust boundary không?
12. Có integration test bằng WebTestClient không?
13. Đã đo latency và memory khi nhiều request render chưa?
14. Có cancellation khi client đóng kết nối không?
15. Có nên tách UI MVC và API WebFlux thành hai ứng dụng không?

## 7. Bài tập tự kiểm tra

1. ViewResolver làm gì? **Ánh xạ tên view logic thành View cụ thể.**
2. View WebFlux render trả kiểu gì? **Mono<Void>.**
3. ViewResolutionResultHandler làm gì? **Resolve view và điều phối render response.**
4. @RestController có tự resolve tên view không? **Không; chuỗi được xử lý theo ResponseBody semantics.**
5. Mono trong model được xử lý ra sao? **Resolve thành một giá trị hoặc rỗng trước khi render.**
6. Flux trong model view thông thường được xử lý ra sao? **Collect thành List trước khi render.**
7. Vì sao Flux vô hạn không phù hợp với model template? **Nó không complete để tạo List và có thể giữ dữ liệu không giới hạn.**
8. Spring Boot hỗ trợ view engine nào cho WebFlux? **FreeMarker, Thymeleaf và Mustache.**
9. Tích hợp Thymeleaf WebFlux dùng resolver nào? **ThymeleafReactiveViewResolver.**
10. Spring có tích hợp FreeMarker cho WebFlux không? **Có, qua FreeMarkerView và FreeMarkerViewResolver.**
11. JSP resolver tiêu chuẩn thuộc framework nào? **Spring MVC trên Servlet stack.**
12. InternalResourceViewResolver dispatch tới đâu? **Servlet resource, đặc biệt JSP.**
13. Chạy WebFlux trên Tomcat có expose Servlet API không? **Không; WebFlux dùng adapter non-blocking.**
14. Vì sao blocking API nguy hiểm trên event loop? **Nó giữ worker thread và làm request khác chờ.**
15. Cách cô lập callable blocking trong Reactor? **Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()).**
16. publishOn sau callable có chuyển source sang scheduler mới không? **Không; subscribeOn điều khiển source subscription.**
17. FreeMarker .ftlh có ý nghĩa gì? **HTML output format có auto-escaping.**
18. WebFlux có hỗ trợ forward: như Servlet không? **Không; dùng redirect hoặc route khác.**
19. Cách render nhiều HTML fragment? **Collection<Fragment>, FragmentsRendering hoặc Flux<Fragment>.**
20. Có thể dùng JSP trực tiếp như view native của WebFlux không? **Không; built-in JSP integration thuộc Spring MVC/Servlet.**

## 8. Ghi nhớ và tài liệu tham khảo

- WebFlux có view resolution riêng qua `ViewResolver`, `View` và `ViewResolutionResultHandler`.
- `View.render` trả `Mono<Void>`, nhưng custom view vẫn có thể block nếu engine gọi API đồng bộ.
- Spring Boot hỗ trợ FreeMarker, Thymeleaf và Mustache cho WebFlux; mỗi engine có giới hạn riêng.
- Thymeleaf có reactive integration và chunked mode khi cấu hình max chunk size.
- FreeMarker có tích hợp WebFlux; một số property chỉ hỗ trợ Spring MVC.
- JSP/JSTL, `InternalResourceViewResolver` và `JstlView` thuộc Spring MVC/Servlet stack.
- Chạy WebFlux trên Tomcat không làm Servlet API/JSP trở thành view native.
- WebFlux resolve Mono model attribute thành giá trị và collect Flux thành List trước khi render view thông thường.
- Dùng `FragmentsRendering` hoặc `Flux<Fragment>` cho HTML fragment streaming.
- Cô lập API blocking bằng `subscribeOn(Schedulers.boundedElastic())`; không block event loop.
- Template phải được bảo vệ trong trust boundary và dữ liệu HTML phải được escape.

Tài liệu chính thức:

1. [Spring Framework 6.2 — View Technologies in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-view.html): Thymeleaf, FreeMarker, script views, HTML fragments và JSON/XML views.
2. [Spring Framework 6.2 — View Resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): ViewResolutionResultHandler, reactive model attributes, content negotiation và redirect.
3. [Spring Framework 6.2 — WebFlux Concurrency Model](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/new-framework.html): event-loop threads, blocking APIs và scheduler.
4. [Spring Framework 6.2 — JSP and JSTL](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-view/mvc-jsp.html): InternalResourceViewResolver, JstlView và JSP tag libraries trên Servlet.
5. [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): template engine auto-configuration, static resources và reactive server.
6. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): FreeMarker và Thymeleaf reactive properties, cùng các giới hạn MVC-only.
7. [Spring Framework 6.2 — FreeMarkerView Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/result/view/freemarker/FreeMarkerView.html): FreeMarker view implementation và render contract.

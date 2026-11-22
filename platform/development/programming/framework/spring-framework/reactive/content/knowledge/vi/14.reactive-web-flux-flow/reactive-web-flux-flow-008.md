# Phân biệt khả năng dùng Servlet container với Servlet API trong ứng dụng

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Luồng xử lý WebFlux

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **Servlet container** (môi trường chạy HTTP) với **Servlet API** (bộ interface lập trình ứng dụng servlet).
2. Giải thích vì sao Spring WebFlux có thể chạy trên Tomcat/Jetty là Servlet container nhưng controller vẫn dùng `ServerHttpRequest`, `ServerHttpResponse`, `ServerWebExchange` và `WebFilter`.
3. Mô tả vai trò của adapter Servlet trong việc nối Servlet non-blocking I/O với reactive `HttpHandler` của Spring.
4. Nhận biết code thuộc Spring MVC/Servlet model và code thuộc Spring WebFlux/reactive server model; không nhầm hai mô hình chỉ vì cả hai có thể chạy trên Tomcat.
5. Chọn dependency và cấu hình phù hợp khi chạy WebFlux bằng Reactor Netty, embedded Tomcat hoặc WAR trên Servlet container bên ngoài.
6. Tránh các lỗi phổ biến: đưa `HttpServletRequest` vào WebFlux controller, dùng Servlet `Filter` thay `WebFilter`, đọc `HttpSession`/ThreadLocal sai cách hoặc vô tình khiến Spring Boot chọn MVC.

## 1. Hai khái niệm khác nhau

“Chạy trên Servlet container” và “dùng Servlet API trong code ứng dụng” mô tả **hai lớp khác nhau**.

- **Servlet container** là runtime/server thực thi hợp đồng Servlet: nhận kết nối HTTP, quản lý web application, triển khai servlet/filter/listener và điều phối request/response. Ví dụ phổ biến là Apache Tomcat và Eclipse Jetty.
- **Servlet API** là bộ interface Java/Jakarta mà ứng dụng servlet có thể lập trình trực tiếp, ví dụ `HttpServletRequest`, `HttpServletResponse`, `HttpSession`, `Filter` và `ServletContext`.

Spring WebFlux có thể được **host bởi một Servlet container**. Khi đó, lớp tích hợp của Spring dùng Servlet API ở ranh giới server để nối container với reactive runtime. Nhưng code xử lý HTTP của ứng dụng WebFlux thông thường dùng **reactive WebFlux API**, không viết controller như một servlet application.

> **WebFlux có thể chạy bên trong Servlet container; điều đó không có nghĩa controller WebFlux được xây dựng theo Servlet API.** Adapter ở tầng tích hợp có thể sử dụng Servlet API nội bộ, còn ứng dụng vẫn làm việc với abstraction reactive của Spring.

Đây không chỉ là khác biệt về tên gọi. Nó quyết định cách viết controller, filter, đọc body, xử lý session, quản lý luồng dữ liệu và tích hợp bảo mật.

## 2. Ba lớp kiến trúc

Một ứng dụng WebFlux có thể dùng runtime khác nhau:

```text
                    HTTP client
                         |
                         v
                 HTTP runtime/server
                         |
             +-----------+-----------+
             |                       |
       Reactor Netty            Tomcat / Jetty
       (không cần               (Servlet container)
        Servlet API)                   |
             |                   Servlet API
             |                         |
             |              Servlet reactive adapter
             |                         |
             +------------+------------+
                          |
                          v
                   Spring HttpHandler
                          |
                          v
                WebFlux WebHandler chain
                          |
              +-----------+-----------+
              |                       |
          WebFilter               HandlerMapping
                                      |
                                      v
                                  Controller
                                      |
                           Mono<T> / Flux<T> body
```

Sơ đồ mô tả các ranh giới khái niệm:

1. **HTTP runtime:** nhận kết nối và truyền dữ liệu. Có thể là Reactor Netty hoặc Servlet container được Spring hỗ trợ.
2. **Server adapter:** chuyển request/response của runtime thành abstraction mà Spring reactive server hiểu. Với Servlet container, adapter tương tác với Servlet API và cơ chế non-blocking I/O của container.
3. **WebFlux application:** xử lý bằng `HttpHandler`, `WebFilter`, `ServerWebExchange`, controller và `Mono`/`Flux`.

Khi chạy với Reactor Netty, không cần Servlet container hay Servlet API để phục vụ HTTP. Khi chạy với Tomcat, Tomcat vẫn là Servlet container, nhưng WebFlux sử dụng adapter reactive để xử lý request. Controller không vì vậy mà trở thành `HttpServlet`.

## 3. Servlet container không đồng nghĩa Spring MVC

Cả Spring MVC và Spring WebFlux đều có thể chạy trên Tomcat. Chúng dùng những mô hình xử lý khác nhau.

| Nội dung | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Mô hình server phía ứng dụng | Servlet-based | Reactive WebHandler/HttpHandler |
| Thành phần điều phối chính | `DispatcherServlet` | `DispatcherHandler` trong WebFlux |
| Request abstraction | `HttpServletRequest` | `ServerHttpRequest` |
| Response abstraction | `HttpServletResponse` | `ServerHttpResponse` |
| Filter ở tầng framework | Servlet `Filter` / `OncePerRequestFilter` | `WebFilter` |
| Session abstraction | Thường là `HttpSession` | `WebSession` |
| Dữ liệu body | Servlet stream/MVC message converters | `Mono<T>`, `Flux<T>`, `Flux<DataBuffer>` |
| Return type | DTO, object, `ResponseEntity`; cũng hỗ trợ reactive return type | DTO, `Mono<T>`, `Flux<T>` và response reactive |
| Runtime phổ biến | Servlet container | Reactor Netty hoặc Servlet container có adapter |

**Tomcat chỉ cho biết runtime**, không đủ để kết luận ứng dụng là MVC hay WebFlux. Phải xem dependency, application type, handler stack và API mà code ứng dụng đang sử dụng.

Một điểm dễ gây nhầm: Spring MVC có thể nhận một số reactive type như `Mono` hoặc `Flux` làm return value và thích nghi với chúng. Việc một controller trả `Mono<String>` **không tự biến ứng dụng MVC thành WebFlux**. Nếu request vẫn đi qua `DispatcherServlet` và Servlet request lifecycle, đó vẫn là Spring MVC.

Tương tự, dùng `WebClient` trong ứng dụng MVC không biến server thành WebFlux. WebClient là HTTP client reactive; server-side programming model được quyết định riêng.

## 4. WebFlux dùng Servlet container bằng cách nào?

Spring WebFlux có abstraction server trung tâm là `HttpHandler`. Runtime-specific adapter nhận request từ server và chuyển nó vào reactive processing chain.

Khi chạy trên Servlet container, Spring cung cấp adapter như `ServletHttpHandlerAdapter`. Adapter này tích hợp với Servlet API, dùng khả năng asynchronous/non-blocking I/O của container để nối request và response với `HttpHandler`.

Điều này có nghĩa:

- Tomcat vẫn nhận kết nối, quản lý socket, triển khai web application và cung cấp Servlet runtime.
- Servlet adapter là cầu nối giữa request/response của container và reactive server API của Spring.
- WebFlux xử lý body và response theo publisher, demand, cancellation và các abstraction reactive.
- Ứng dụng không phải tự viết `HttpServlet` hoặc gọi `HttpServletRequest.getInputStream()` để đọc body trong controller.
- Việc dùng Servlet container **không tự biến các thao tác blocking trong ứng dụng thành non-blocking**.

### 4.1. Servlet non-blocking I/O

Khả năng tích hợp reactive qua Servlet dựa vào API non-blocking I/O được bổ sung trong Servlet 3.1, như đọc/ghi theo callback và trạng thái sẵn sàng của stream. Spring adapter dùng cơ chế này để kết nối với reactive pipeline thay vì bắt ứng dụng tự quản lý Servlet input/output stream.

Khi triển khai Spring Boot 3, còn phải xét **Jakarta namespace và phiên bản container tương thích**. Ví dụ dự án Boot 3.3.x sử dụng Tomcat 10.1. Không thể lấy một container cũ dùng `javax.servlet` rồi giả định tương thích với ứng dụng Spring Boot 3 dùng `jakarta.servlet`.

### 4.2. Adapter dùng Servlet API nội bộ không có nghĩa ứng dụng nên dùng nó

Một adapter có thể cần các kiểu Servlet để nhận callback từ container. Đây là chi tiết của lớp tích hợp. Ứng dụng WebFlux vẫn nên lập trình theo các abstraction công khai của WebFlux:

- Đọc request: `ServerHttpRequest` hoặc `ServerWebExchange`.
- Ghi response: `ServerHttpResponse` hoặc return body từ controller.
- Filter: `WebFilter`.
- Session: `WebSession`.
- Thông tin xác thực: `Principal` và Spring Security reactive.
- Request-scoped metadata: exchange attributes hoặc Reactor `Context`.

Không nên lấy đối tượng Servlet nội bộ từ adapter để xây dựng logic nghiệp vụ phụ thuộc container. Làm vậy sẽ khiến code khó chạy trên Reactor Netty và giảm tính portable của WebFlux.

## 5. Nhìn code để nhận biết programming model

### 5.1. WebFlux controller

```java
@RestController
public class ReactiveController {
    @GetMapping("/profile")
    public Mono<String> profile(ServerHttpRequest request) {
        String method = request.getMethodValue();
        String path = request.getPath().value();
        return Mono.just(method + " " + path);
    }
}
```

Đây là **đoạn minh họa controller WebFlux**. Method nhận `ServerHttpRequest` và trả `Mono<String>`. Hạ tầng WebFlux tiêu thụ publisher để tạo HTTP response. Controller không nhận `HttpServletRequest` và không cần tự gọi `subscribe()`.

### 5.2. Spring MVC controller dùng Servlet API

```java
@RestController
public class ServletController {
    @GetMapping("/profile")
    public String profile(HttpServletRequest request) {
        return request.getMethod() + " " + request.getRequestURI();
    }
}
```

Đây là **đoạn minh họa Spring MVC**, cần import `jakarta.servlet.http.HttpServletRequest` trong ứng dụng Spring Boot 3 và dùng MVC stack phù hợp. `HttpServletRequest` là Servlet API. Không lấy ví dụ này rồi đưa nguyên vào controller WebFlux.

### 5.3. So sánh filter

Servlet filter có hợp đồng kiểu:

```java
void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException;
```

`WebFilter` của WebFlux có hợp đồng reactive:

```java
Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain);
```

Một Servlet filter chạy trong Servlet filter chain; một WebFilter nằm trong WebFlux WebHandler chain. Dù WebFlux đang được host bởi Tomcat, hai filter này vẫn có **hợp đồng và vị trí xử lý khác nhau**. Trong logic ứng dụng WebFlux, ưu tiên `WebFilter`. Servlet filter chỉ nên được thêm khi có yêu cầu tích hợp ở ranh giới Servlet container và đã hiểu rõ async dispatch/lifecycle.

## 6. Chạy WebFlux trên embedded Tomcat: ví dụ Java 17+

Ví dụ này minh họa đúng ý chính: ứng dụng sử dụng **Tomcat làm server runtime**, nhưng code controller dùng reactive API. Dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5**.

Cấu trúc dự án:

```text
webflux-on-tomcat/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── WebFluxTomcatApplication.java
    │   ├── RequestTraceWebFilter.java
    │   └── ApiController.java
    └── resources/
        └── application.properties
```

### 6.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-on-tomcat</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
            <exclusions>
                <exclusion>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-reactor-netty</artifactId>
                </exclusion>
            </exclusions>
        </dependency>

        <!-- Tomcat là server container; WebFlux vẫn là application model. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
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

Ở đây, ta loại starter Reactor Netty khỏi WebFlux starter và thêm Tomcat starter. Dự án **không** thêm `spring-boot-starter-web`, nên không đưa Spring MVC/DispatcherServlet vào chỉ để chạy trên Tomcat. Tomcat cung cấp server container; Spring Boot cấu hình reactive server adapter tương ứng.

### 6.2. application.properties

```properties
spring.main.web-application-type=reactive
server.port=8080
```

Đặt application type tường minh để ví dụ tập trung vào reactive web application. Với cấu hình dependency chỉ có WebFlux như trên, Boot thường có thể suy ra reactive type; thuộc tính này giúp tránh nhầm lẫn khi thay đổi dependency trong lúc học.

### 6.3. WebFluxTomcatApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxTomcatApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxTomcatApplication.class, args);
    }
}
```

### 6.4. RequestTraceWebFilter.java

```java
package demo;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class RequestTraceWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = UUID.randomUUID().toString();
        exchange.getAttributes().put("demo.requestId", requestId);
        exchange.getResponse().getHeaders()
                .set("X-Request-Id", requestId);

        return chain.filter(exchange)
                .doFinally(signal ->
                        System.out.println(
                                "request " + requestId + " -> " + signal));
    }
}
```

Filter dùng `ServerWebExchange` và `WebFilter`. Không có `jakarta.servlet.Filter`, `HttpServletRequest` hay `HttpServletResponse` trong code ứng dụng. Header được đặt trước khi chain xử lý response. `doFinally` ghi nhận kết cục complete/error/cancel ở vị trí publisher này.

### 6.5. ApiController.java

```java
package demo;

import java.time.Duration;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {
    public record RuntimeInfo(
            String application,
            String method,
            String path,
            String requestId) {}

    @GetMapping("/api/runtime")
    public Mono<RuntimeInfo> runtime(
            ServerHttpRequest request,
            ServerWebExchange exchange) {

        String requestId = exchange.getAttributeOrDefault(
                "demo.requestId", "missing");

        return Mono.just(new RuntimeInfo(
                "Spring WebFlux",
                request.getMethodValue(),
                request.getPath().value(),
                requestId));
    }

    @PostMapping(
            value = "/api/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> echo(@RequestBody Mono<String> body) {
        return body.map(value -> "echo: " + value);
    }

    @GetMapping(
            value = "/api/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Long> ticks() {
        return Flux.interval(Duration.ofMillis(500)).take(3);
    }

    @GetMapping("/api/manual-response")
    public Mono<Void> manualResponse(ServerHttpResponse response) {
        response.setStatusCode(HttpStatus.ACCEPTED);
        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

        byte[] bytes = "written through ServerHttpResponse\n"
                .getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = response.bufferFactory().wrap(bytes);

        return response.writeWith(Mono.just(buffer));
    }
}
```

Controller sử dụng bốn kiểu reactive/server-side:

- `ServerHttpRequest` để đọc method và path.
- `ServerWebExchange` để đọc request attribute.
- `ServerHttpResponse` để ghi response ở endpoint đặc biệt.
- `Mono`/`Flux` để biểu diễn body và streaming.

Không có một Servlet API nào được dùng trực tiếp trong controller. Tomcat vẫn là container ở bên dưới.

### 6.6. Chạy thử

Tại thư mục có `pom.xml`:

```bash
mvn spring-boot:run
```

Trong log khởi động, kiểm tra server được chọn là Tomcat (dòng khởi động Tomcat), không phải Reactor Netty.

Trên Windows PowerShell dùng `curl.exe` để tránh alias `curl`; trên Linux/macOS có thể dùng `curl`:

```powershell
curl.exe -i http://localhost:8080/api/runtime
curl.exe -i -X POST -H "Content-Type: text/plain" --data "hello" http://localhost:8080/api/echo
curl.exe -i http://localhost:8080/api/manual-response
curl.exe -N http://localhost:8080/api/ticks
```

**Kết quả cần quan sát:**

1. `GET /api/runtime` trả HTTP 200, JSON có `application` là `Spring WebFlux`, method `GET`, path `/api/runtime` và request ID. Header `X-Request-Id` có cùng giá trị với trường request ID.
2. `POST /api/echo` với body `hello` trả body `echo: hello`.
3. `GET /api/manual-response` trả HTTP 202 Accepted và body `written through ServerHttpResponse`.
4. `GET /api/ticks` phát ba event số theo thời gian qua `text/event-stream`. Dùng `-N` để curl không gom buffer khi hiển thị.

Ví dụ log filter (request ID thay đổi mỗi lần):

```text
request <request-id> -> onComplete
request <request-id> -> onComplete
request <request-id> -> onComplete
request <request-id> -> onComplete
```

Đây là hình dạng log khi các request hoàn tất bình thường; stream có thể bị cancel nếu client ngắt trước khi ba event được phát.

**Ý nghĩa của ví dụ:** Tomcat là Servlet container và cung cấp môi trường Servlet ở lớp server, nhưng controller và WebFilter vẫn dùng reactive WebFlux API. Việc thêm Tomcat không bắt buộc ta chuyển code sang Spring MVC.

## 7. Triển khai WebFlux thành WAR trên Servlet container bên ngoài

Ngoài embedded Tomcat, WebFlux có thể được đóng gói thành WAR để triển khai vào Servlet container tương thích. Đây là lựa chọn deployment; nó không thay đổi application programming model.

### 7.1. Application initializer

Với Spring Boot, class ứng dụng có thể mở rộng `SpringBootServletInitializer` để container bên ngoài khởi tạo Spring application:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WebFluxWarApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(WebFluxWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WebFluxWarApplication.class, args);
    }
}
```

Đây là **đoạn cấu hình cho WAR deployment**. Việc mở rộng `SpringBootServletInitializer` là cầu nối để Servlet container khởi động ứng dụng Spring Boot. Các controller WebFlux bên trong vẫn nhận `ServerHttpRequest`/`ServerWebExchange` và trả `Mono`/`Flux`.

### 7.2. Những thay đổi build thường cần

- Đặt packaging Maven thành `war`.
- Loại `spring-boot-starter-reactor-netty` nếu muốn chạy bằng Servlet container.
- Đặt `spring-boot-starter-tomcat` ở scope `provided` khi Tomcat bên ngoài cung cấp runtime.
- Chọn phiên bản Tomcat tương thích với phiên bản Spring Boot/Jakarta Servlet của ứng dụng.
- Không đóng gói một bản Servlet API cũ hoặc xung đột namespace vào WAR.

Ví dụ dependency Tomcat cho WAR:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

Đoạn trên là **phần cấu hình thay cho dependency Tomcat embedded** ở ví dụ trước; không giữ cả hai khai báo Tomcat khác scope. Phần WebFlux starter vẫn loại Reactor Netty như trong ví dụ. Khi triển khai, container phải đáp ứng baseline Jakarta mà phiên bản Boot yêu cầu; ví dụ Boot 3.3.x thường đi cùng Tomcat 10.1. Tomcat 9 dùng namespace `javax.servlet` nên không tương thích trực tiếp với ứng dụng Boot 3 dùng `jakarta.servlet`.

**Phân biệt:** `SpringBootServletInitializer` là integration bootstrap cho deployment Servlet container. Sự hiện diện của class này không có nghĩa bạn phải viết controller bằng `HttpServletRequest`.

## 8. Khi nào thật sự cần Servlet API trong code?

Có những ứng dụng cần tích hợp thư viện hoặc thành phần cũ vốn được thiết kế riêng cho Servlet API. Trước khi đưa chúng vào WebFlux, hãy xác định ranh giới:

- Nếu thành phần chỉ cần chạy trong một Servlet container, có thể chỉ cần triển khai WebFlux trên Tomcat/Jetty; code nghiệp vụ vẫn giữ reactive API.
- Nếu thư viện yêu cầu `HttpServletRequest`/`HttpServletResponse` hoặc Servlet Filter, nó phụ thuộc Servlet programming model. Cần adapter hoặc ranh giới tích hợp rõ ràng; không giả định WebFlux controller sẽ cung cấp các kiểu đó.
- Nếu tính năng phụ thuộc ThreadLocal, request-bound state hoặc synchronous Servlet callback, cần đánh giá lại vì reactive chain có thể đổi thread và nhiều request có thể đan xen.
- Nếu logic chỉ cần method/header/path/body, hãy dùng `ServerHttpRequest`; nếu cần request/response/session/principal cùng lúc, dùng `ServerWebExchange`.
- Nếu yêu cầu thực sự là xây dựng ứng dụng Servlet/MVC truyền thống, hãy chọn Spring MVC và dùng Servlet API đúng mô hình thay vì ép Servlet programming model vào WebFlux.

### 8.1. Dùng Servlet Filter ở ngoài adapter có được không?

Trong deployment trên Servlet container, một Servlet Filter có thể nằm ở filter chain của container và bao quanh servlet adapter. Điều này hữu ích cho một số tích hợp ở ranh giới Servlet, nhưng cần hiểu rằng:

- Nó chạy theo Servlet filter lifecycle và có thể nhận Servlet request/response.
- Nó bao quanh WebFlux adapter, không thay thế các WebFilter bên trong reactive chain.
- Các thao tác async dispatch và non-blocking I/O phải tuân thủ hợp đồng của Servlet container.
- Không được chặn thread hoặc đọc body tùy tiện rồi mong WebFlux decoder vẫn nhận lại cùng stream.
- Nếu concern thuộc logic HTTP reactive của ứng dụng, `WebFilter` thường là vị trí phù hợp hơn và có thể dùng trên nhiều runtime.

Đừng đăng ký cùng một logic xác thực ở cả Servlet Filter và WebFilter mà không có thiết kế rõ; có thể dẫn tới kiểm tra trùng, thứ tự khó hiểu hoặc khác biệt giữa runtime.

## 9. Các abstraction thay thế thường dùng trong WebFlux

| Nhu cầu trong Servlet code | WebFlux abstraction thường dùng | Lưu ý |
| --- | --- | --- |
| `HttpServletRequest` | `ServerHttpRequest` / `ServerWebExchange` | Đọc request metadata và body reactive. |
| `HttpServletResponse` | `ServerHttpResponse` | Đặt status/header và ghi body qua publisher. |
| `Filter` / `OncePerRequestFilter` | `WebFilter` | Trả `Mono<Void>` và compose chain. |
| `HttpSession` | `WebSession` qua `exchange.getSession()` | Session API reactive, không block để lấy. |
| Request attributes | `exchange.getAttributes()` | Scope của một exchange/request. |
| ThreadLocal request context | Reactor `Context`, exchange attributes, tracing | Không giả định cùng thread xử lý toàn bộ pipeline. |
| Servlet async request handling | `Mono`/`Flux` + reactive server runtime | Backpressure/cancel được biểu diễn bằng Reactive Streams. |
| Servlet multipart parsing | WebFlux multipart reader, `Part`/`PartEvent` | Chọn cách parse/stream phù hợp kích thước body. |
| Servlet input/output stream | `Flux<DataBuffer>` và response write API | Cần hiểu buffer ownership, release và cancellation. |

Không phải mỗi Servlet API đều có một thay thế một-một trong WebFlux. Ví dụ `ServletContext` là abstraction của Servlet container; trong ứng dụng Spring, nhiều nhu cầu cấu hình/lifecycle thuộc `ApplicationContext`, `Environment` hoặc bean lifecycle. Hãy chuyển theo **ý nghĩa nghiệp vụ**, không đổi tên class máy móc.

### 9.1. Session và principal

```java
Mono<String> userName = exchange.getPrincipal()
        .map(Principal::getName)
        .defaultIfEmpty("anonymous");

Mono<WebSession> session = exchange.getSession();
```

Đây là **đoạn minh họa** trong handler/filter, cần import `Principal` và `WebSession`. Không gọi `block()` để lấy session hoặc principal trên event-loop. Với xác thực/phân quyền, dùng Spring Security reactive thay vì tự tin tưởng header hoặc lưu user hiện tại vào field singleton.

### 9.2. Request context không phải ThreadLocal

Servlet application đồng bộ thường dựa vào việc một request được xử lý trên một thread tại một thời điểm nhất định. Reactive pipeline có thể tiếp tục trên thread khác do scheduler, I/O callback hoặc operator. Vì vậy, không lưu request ID, user ID hay transaction context trong một `ThreadLocal` mutable rồi giả định mọi callback đều đọc đúng request.

Dùng Reactor `Context` hoặc `ServerWebExchange.getAttributes()` tùy phạm vi dữ liệu. Context gắn với subscription; attributes gắn với exchange. Cả hai phù hợp hơn cho dữ liệu theo request trong reactive flow.

## 10. Dependency và lựa chọn runtime

### 10.1. WebFlux mặc định thường dùng Reactor Netty

`spring-boot-starter-webflux` mặc định đưa Reactor Netty vào khi không thay server. Đây là lựa chọn phổ biến cho reactive server không cần Servlet container. Nếu muốn dùng Tomcat hoặc Jetty, loại server starter mặc định và thêm server starter tương ứng theo hướng dẫn của phiên bản Spring Boot.

### 10.2. Đừng thêm spring-boot-starter-web chỉ vì muốn Tomcat

`spring-boot-starter-web` đưa Spring MVC và embedded Servlet server vào. Nếu cùng có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường ưu tiên cấu hình MVC khi cả hai stack đều có mặt. Khi đó, ứng dụng có thể chạy bằng Tomcat nhưng **application model là MVC**, dù dependency WebFlux cũng tồn tại.

Muốn WebFlux server, thường chỉ cần `spring-boot-starter-webflux` và chọn server runtime phù hợp. Để dùng Tomcat, thêm `spring-boot-starter-tomcat` sau khi loại Reactor Netty như ví dụ.

### 10.3. Không suy ra programming model từ return type

Spring MVC có khả năng thích nghi một số reactive return type. Ví dụ MVC controller có thể trả `Mono<ResponseEntity<?>>` nhưng request vẫn đi qua Servlet/MVC infrastructure. Ngược lại, WebFlux controller trả DTO thường vẫn được WebFlux xử lý reactive; không bắt buộc mọi method phải trả `Flux`.

Hãy xác định stack qua cấu hình và server factory, không chỉ qua chữ `Mono` trong method signature.

### 10.4. Phiên bản namespace quan trọng

Spring Boot 2 và Spring Framework 5 thuộc hệ sinh thái `javax.servlet`; Spring Boot 3 và Spring Framework 6 dùng `jakarta.servlet`. Các dependency, filter và container phải tương thích namespace/phiên bản. Không trộn class `javax.servlet.*` vào ứng dụng Boot 3 đang dùng `jakarta.servlet.*`; hai package khác nhau dù tên type gần giống.

## 11. Non-blocking không tự động chỉ vì chạy trên Tomcat

Một Servlet container hỗ trợ non-blocking I/O là điều kiện để adapter có thể tích hợp reactive server. Nhưng điều đó không biến mọi code của ứng dụng thành non-blocking.

```java
@GetMapping("/legacy")
public Mono<String> legacy() {
    return Mono.fromCallable(() -> jdbcTemplate.queryForObject(
            "select message from greeting where id = 1",
            String.class))
        .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là **đoạn minh họa**: `jdbcTemplate` và import do ứng dụng cung cấp. `fromCallable` trì hoãn lời gọi và chuyển exception thành tín hiệu lỗi, còn `subscribeOn(boundedElastic())` cô lập thao tác blocking trên scheduler phù hợp. JDBC vẫn là blocking; không thể gọi nó là non-blocking chỉ vì server là WebFlux/Tomcat.

Tốt hơn, khi có thể, dùng API reactive như R2DBC và WebClient. Dù chạy Netty hay Tomcat, một thao tác blocking đặt trên thread xử lý I/O vẫn có thể làm giảm khả năng phục vụ request và tăng latency.

## 12. Chọn đúng mô hình theo yêu cầu

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Ứng dụng reactive mới, không cần Servlet ecosystem | WebFlux + Reactor Netty. |
| Ứng dụng WebFlux phải chạy trên hạ tầng doanh nghiệp chuẩn hóa Tomcat | WebFlux + reactive Tomcat adapter; code ứng dụng vẫn dùng WebFlux API. |
| Cần triển khai WAR vào Servlet container được hỗ trợ | WebFlux WAR + `SpringBootServletInitializer` và container tương thích Jakarta. |
| Ứng dụng legacy dựa sâu vào `HttpServletRequest`, Servlet Filter và HttpSession | Cân nhắc Spring MVC/Servlet model hoặc thiết kế ranh giới tích hợp riêng. |
| Cần giữ controller MVC nhưng muốn gọi HTTP bất đồng bộ | Có thể dùng WebClient; server không vì thế trở thành WebFlux. |
| Chỉ cần streaming/reactive return value trong MVC | Đánh giá khả năng reactive adapter của MVC; không nhầm với WebFlux server stack. |

Không có lựa chọn nào tốt nhất cho mọi hệ thống. Hãy xem thư viện tích hợp hiện có, deployment standard, nhu cầu streaming, cách quản lý I/O và năng lực vận hành. Đừng chuyển sang WebFlux chỉ vì muốn dùng Tomcat mới; cũng đừng bỏ WebFlux chỉ vì tổ chức đang chuẩn hóa Servlet container.

## 13. Lỗi thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “WebFlux chạy Tomcat nên controller dùng `HttpServletRequest`.” | Tomcat là runtime; WebFlux controller dùng reactive server abstraction. | Dùng `ServerHttpRequest`/`ServerWebExchange`. |
| “Có Servlet API trên classpath nghĩa là app đang chạy MVC.” | Servlet API có thể được container/adapter dùng để host WebFlux. | Kiểm tra web application type, starter và server factory. |
| “Dùng `Mono` là app chắc chắn WebFlux.” | Spring MVC cũng có reactive return type adapter. | Kiểm tra MVC/DispatcherServlet hay WebFlux/DispatcherHandler stack. |
| Thêm `spring-boot-starter-web` chỉ để lấy Tomcat | Có thể khiến Boot ưu tiên MVC khi cả hai stack cùng có mặt. | Dùng WebFlux starter và thêm Tomcat server starter riêng. |
| Dùng Servlet `Filter` cho mọi logic WebFlux | Servlet filter thuộc container chain, không phải reactive WebFilter chain. | Dùng `WebFilter` cho concern reactive của ứng dụng. |
| Dùng `HttpSession` trực tiếp trong controller WebFlux | Không phải abstraction session reactive chuẩn của WebFlux. | Dùng `WebSession` qua exchange. |
| Lưu request data trong ThreadLocal | Reactive flow có thể đổi thread và nhiều request đan xen. | Dùng Reactor Context hoặc exchange attributes. |
| Gọi `block()` để lấy request body/principal | Chặn thread và phá reactive lifecycle. | Compose publisher bằng `map`/`flatMap`. |
| Đọc Servlet input stream rồi để WebFlux decoder đọc tiếp | Body có thể đã bị tiêu thụ; request body là stream một lần. | Dùng codec hoặc replay strategy được quản lý rõ. |
| Tưởng Tomcat biến JDBC blocking thành non-blocking | Container không thay đổi bản chất I/O của thư viện. | Dùng reactive driver hoặc cô lập blocking work. |
| Deploy Boot 3 WAR lên container chỉ có javax Servlet | Namespace không tương thích. | Dùng Jakarta-compatible container đúng phiên bản. |
| Cho rằng Servlet container luôn cần thiết cho WebFlux | Reactor Netty có thể chạy WebFlux độc lập. | Chọn runtime theo yêu cầu deployment. |
| Cho rằng WebFlux không thể chạy trên Servlet container | WebFlux có Servlet adapter hỗ trợ container tương thích. | Cấu hình adapter/server starter đúng phiên bản. |
| Dùng Servlet request trong shared service để đọc request hiện tại | Tạo phụ thuộc container và request-thread assumptions. | Truyền dữ liệu cần thiết qua tham số hoặc reactive context. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Servlet container và Servlet API khác nhau ở đâu?  
**Đáp án:** Container là runtime triển khai và thực thi ứng dụng web; Servlet API là các interface Java/Jakarta mà code servlet dùng để xử lý request, response, session và filter.

**Câu 2.** WebFlux có chạy trên Tomcat được không?  
**Đáp án:** Có. Spring cung cấp adapter để tích hợp reactive HttpHandler với Servlet container tương thích. Tomcat vẫn là Servlet container, nhưng controller WebFlux dùng reactive API.

**Câu 3.** Nếu controller nhận `ServerHttpRequest` thì có nghĩa ứng dụng không dùng Servlet API ở bất kỳ lớp nào không?  
**Đáp án:** Không. Khi host trên Tomcat, adapter có thể dùng Servlet API nội bộ. Điều quan trọng là application code không phụ thuộc Servlet API như programming model chính.

**Câu 4.** `WebFilter` và Servlet `Filter` có giống nhau không?  
**Đáp án:** Không. Chúng ở hai chain khác nhau và có hợp đồng khác nhau: `WebFilter` trả `Mono<Void>`; Servlet Filter dùng `doFilter` với Servlet request/response và FilterChain.

**Câu 5.** Ứng dụng có cả `spring-boot-starter-web` và `spring-boot-starter-webflux` thì Boot thường chọn gì?  
**Đáp án:** Khi cả hai stack có mặt, Spring Boot thường ưu tiên Spring MVC. Muốn WebFlux server, không thêm MVC starter nếu không thực sự cần; chọn server runtime bằng dependency phù hợp.

**Câu 6.** Dùng `Mono<String>` làm return type có chứng minh controller là WebFlux không?  
**Đáp án:** Không. Spring MVC cũng có thể thích nghi reactive return type. Phải xem toàn bộ server stack và application type.

**Câu 7.** Nếu dùng Tomcat với WebFlux, có thể dùng `HttpSession` thay `WebSession` không?  
**Đáp án:** Trong WebFlux application model, dùng `WebSession`. Việc container có Servlet session API không có nghĩa nên đưa Servlet session vào reactive handler.

**Câu 8.** Tomcat non-blocking adapter có làm JDBC đồng bộ trở thành non-blocking không?  
**Đáp án:** Không. JDBC vẫn blocking. Dùng driver reactive hoặc chuyển tác vụ blocking sang scheduler phù hợp.

**Câu 9.** Boot 3 dùng package Servlet nào?  
**Đáp án:** `jakarta.servlet.*`. Không trộn với `javax.servlet.*` của hệ sinh thái cũ.

## Ghi nhớ

- **Servlet container là nơi chạy; Servlet API là bộ interface để lập trình theo Servlet model.**
- Spring WebFlux có thể chạy trên Reactor Netty hoặc Servlet container như Tomcat/Jetty thông qua adapter phù hợp.
- Khi WebFlux chạy trên Tomcat, adapter có thể dùng Servlet API ở lớp tích hợp; controller và filter của ứng dụng vẫn nên dùng `ServerHttpRequest`, `ServerHttpResponse`, `ServerWebExchange` và `WebFilter`.
- Chạy trên Tomcat không tự biến WebFlux thành Spring MVC. Ngược lại, dùng `Mono` trong Spring MVC cũng không tự biến MVC thành WebFlux.
- Muốn dùng WebFlux với Tomcat, chọn WebFlux starter và Tomcat server dependency, tránh vô tình thêm MVC starter; kiểm tra application type và Jakarta compatibility.
- Non-blocking phụ thuộc toàn bộ pipeline. JDBC/blocking call vẫn blocking dù ứng dụng chạy trên reactive server.

### Tài liệu tham khảo

1. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): kiến trúc reactive server và các runtime được hỗ trợ.
2. [Spring Framework – Reactive Web Server API](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): `HttpHandler`, server adapters, `ServerWebExchange` và `WebFilter`.
3. [Spring Framework – ServerHttpRequest Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html): request abstraction của reactive server.
4. [Spring Framework – ServletHttpHandlerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServletHttpHandlerAdapter.html): cầu nối Servlet container với reactive `HttpHandler`.
5. [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): cấu hình WebFlux và server runtime.
6. [Spring Boot – Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html): triển khai WAR và `SpringBootServletInitializer`.
7. [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): Servlet API, async processing và non-blocking I/O.

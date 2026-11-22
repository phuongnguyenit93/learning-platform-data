# HandlerMapping và lựa chọn Controller hoặc handler chức năng trong Spring MVC

> **Phạm vi:** Spring Boot 3.5.x, Java 17+, Spring Framework 6.2 và **Spring MVC trên Servlet stack**. Bài này giải thích cách một HTTP request được định tuyến từ `DispatcherServlet` đến controller có annotation hoặc `HandlerFunction` trong WebMvc.fn, vai trò của `HandlerMapping` và `HandlerAdapter`, thứ tự ưu tiên, cách lựa chọn mô hình lập trình, ví dụ Maven chạy được và cách kiểm thử/khắc phục sự cố. Không nhầm WebMvc.fn với WebFlux.fn: chúng có tên API gần giống nhưng thuộc hai web stack khác nhau.

## 1. HandlerMapping giải quyết câu hỏi gì?

HTTP server đã nhận một request, ví dụ:

~~~http
GET /api/annotated/hello?name=Lan HTTP/1.1
Host: localhost:8080
Accept: text/plain
~~~

`DispatcherServlet` là front controller của Spring MVC. Trước khi gọi code nghiệp vụ, nó cần tìm **handler nào chịu trách nhiệm xử lý request**. Spring MVC tách hai việc:

1. **Tìm handler phù hợp:** giao cho một hoặc nhiều triển khai của `HandlerMapping`.
2. **Thực thi handler đã tìm được:** giao cho một `HandlerAdapter` tương thích với loại handler đó.

Về ý nghĩa, `HandlerMapping` thực hiện phép ánh xạ:

~~~text
HttpServletRequest
       |
       v
HandlerMapping.getHandler(request)
       |
       +-- không khớp => thử HandlerMapping kế tiếp
       |
       +-- khớp => HandlerExecutionChain
                        |
                        +-- handler
                        +-- HandlerInterceptor[] (nếu có)
~~~

`HandlerExecutionChain` chứa handler và có thể kèm interceptor. Nó **không phải** một response HTTP. Sau bước này, Spring MVC mới chọn adapter, thực thi handler, xử lý trả về và tạo response.

Các khái niệm dễ nhầm:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| `HandlerMapping` | Request này khớp với handler nào? | `RequestMappingHandlerMapping`, `RouterFunctionMapping` |
| `HandlerAdapter` | Gọi handler thuộc kiểu đó như thế nào? | `RequestMappingHandlerAdapter`, `HandlerFunctionAdapter` |
| Handler | Code thực sự giải quyết request | Method trong `@RestController` hoặc `HandlerFunction<ServerResponse>` |
| `HandlerInterceptor` | Thực hiện hook trước/sau handler MVC | Logging, kiểm soát luồng ở tầng MVC |
| `HandlerExceptionResolver` | Biến ngoại lệ của quá trình dispatch thành kết quả HTTP | Xử lý `@ExceptionHandler`, `ResponseStatusException` |
| `HttpMessageConverter` | Chuyển body giữa Java object và HTTP representation | Jackson JSON, text |
| Servlet Filter | Can thiệp trước/sau `DispatcherServlet` ở tầng Servlet | Security filter chain, correlation ID |

**Đừng gọi `HandlerMapping` là code thực thi controller:** nó chỉ chọn handler/chuỗi interceptor. Cũng đừng gọi mọi handler là một `@Controller`: WebMvc.fn dùng đối tượng hàm.

## 2. Luồng DispatcherServlet và điểm tham gia của HandlerMapping

Luồng đơn giản hóa của request trong ứng dụng Spring MVC:

~~~text
Client HTTP request
         |
         v
Embedded Servlet server (Tomcat/Jetty/Undertow)
         |
         v
Servlet Filter chain (ví dụ Spring Security)
         |
         v
DispatcherServlet
         |
         +--> kiểm tra multipart và thông tin request
         |
         +--> duyệt các HandlerMapping theo thứ tự Order
         |       |
         |       +--> RequestMappingHandlerMapping?
         |       +--> RouterFunctionMapping?
         |       +--> resource/view/default mappings?
         |       +--> ... dừng ở mapping đầu tiên trả handler
         |
         +--> HandlerExecutionChain(handler, interceptors)
         |
         +--> chọn HandlerAdapter hỗ trợ loại handler
         |
         +--> interceptor.preHandle(...)
         |
         +--> adapter.handle(...) gọi handler
         |       |
         |       +--> controller method (annotation)
         |       +--> HandlerFunction (WebMvc.fn)
         |
         +--> xử lý result / response body / view
         +--> interceptor.postHandle / afterCompletion
         +--> HandlerExceptionResolver nếu có lỗi phù hợp
         |
         v
HTTP response
~~~

Sơ đồ lược bỏ nhiều chi tiết như conditional requests, async dispatch và quá trình hoàn tất view. Nó chỉ nhằm thể hiện nơi Spring MVC chọn handler và adapter.

Nếu không có mapping nào xử lý request, ứng dụng thường trả 404 hoặc đi qua cơ chế phục vụ static resource rồi trả 404. Nếu URL khớp controller nhưng HTTP method hoặc media type không hợp lệ, Spring MVC có thể trả 405, 406 hoặc 415 tùy điều kiện mapping. Trạng thái cụ thể phụ thuộc tập mapping, filter và exception resolver đang cài.

### Thứ tự giữa nhiều HandlerMapping

Spring MVC duyệt `HandlerMapping` theo `Ordered` hoặc `@Order`: số **nhỏ hơn** được ưu tiên trước. Trong cấu hình MVC Java chuẩn của Spring Framework 6.2, các mapping tiêu biểu là:

| Triển khai | Order điển hình | Mục đích |
|---|---:|---|
| `RouterFunctionMapping` | -1 | Chọn `HandlerFunction` được khai báo bằng WebMvc.fn |
| `RequestMappingHandlerMapping` | 0 | Chọn method có `@RequestMapping`, `@GetMapping`, ... |
| Mapping của view controller | 1 | Gắn URL trực tiếp với view name |
| `BeanNameUrlHandlerMapping` | 2 | Tên bean tương ứng URL |
| Mapping static resources | `Integer.MAX_VALUE - 1` | Phục vụ file tĩnh |
| Mapping default servlet | `Integer.MAX_VALUE` | Forward sang default servlet nếu cấu hình |

**Các giá trị trên là của cấu hình MVC tiêu chuẩn; người phát triển có thể đăng ký thêm mapping hoặc tùy chỉnh thứ tự.** Đừng suy ra thứ tự thực tế nếu ứng dụng có custom `HandlerMapping`.

Điểm đáng lưu ý là **WebMvc.fn có thể được xem xét trước controller annotation** vì `RouterFunctionMapping` thường có order -1. Nếu một route chức năng và một annotated controller đăng ký **cùng method/path**, không nên coi controller annotation chắc chắn được gọi; với thứ tự chuẩn, functional route phù hợp có thể thắng. Tốt nhất tránh trùng route và kiểm thử khi chuyển đổi mô hình lập trình.

## 3. Controller bằng annotation: RequestMappingHandlerMapping

Mô hình annotation thường dùng:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public String getOne(@PathVariable String id) {
        return "order:" + id;
    }
}
~~~

`RequestMappingHandlerMapping` phát hiện các method phù hợp khi ứng dụng khởi động, đăng ký các điều kiện của request mapping và tìm `HandlerMethod` khi có request đến. `HandlerMethod` đại diện cho method Java của một bean, kèm metadata liên quan.

`RequestMappingHandlerAdapter` biết cách gọi `HandlerMethod`. Nó giải quyết `@PathVariable`, `@RequestParam`, `@RequestBody`, validation, các argument resolver và xử lý giá trị trả về. Với `@RestController`, thông thường giá trị trả về được ghi vào HTTP body thông qua cơ chế return-value handler và message converter.

Những yếu tố được dùng để quyết định match không chỉ có URL:

- HTTP method: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`...
- Path pattern: literal path, path variable, wildcard theo cú pháp hỗ trợ.
- Request parameters: điều kiện `params` trên `@RequestMapping`.
- Headers: điều kiện `headers`.
- `consumes`: định dạng request body, liên quan `Content-Type`.
- `produces`: định dạng response được chấp nhận, liên quan `Accept`.

Ví dụ một method chỉ xử lý JSON:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public OrderReceipt create(@RequestBody CreateOrder request) {
    return new OrderReceipt(request.id(), true);
}
~~~

Đây là **mã minh họa bên trong controller**; `CreateOrder`/`OrderReceipt` là DTO nghiệp vụ cần định nghĩa. Không coi đoạn này là file Java độc lập.

Với **nhiều annotated mapping cùng khớp**, `RequestMappingHandlerMapping` áp dụng thuật toán so độ cụ thể của các điều kiện để chọn handler tốt nhất. Ví dụ một path literal thường cụ thể hơn một path variable phù hợp. Nếu hai handler vẫn bất phân thắng bại, có thể xuất hiện lỗi ambiguous handler; hai mapping trùng hẳn có thể làm ứng dụng fail ngay khi startup.

## 4. Handler chức năng WebMvc.fn: RouterFunctionMapping

Spring MVC cung cấp mô hình **WebMvc.fn** từ package `org.springframework.web.servlet.function`. Mô hình này vẫn chạy trên **cùng DispatcherServlet và Servlet stack** như annotated controllers.

Hai abstraction chính:

- `RouterFunction<ServerResponse>`: kiểm tra một `ServerRequest`; nếu khớp, trả về `HandlerFunction` phù hợp. Router định nghĩa **điều kiện chọn**.
- `HandlerFunction<ServerResponse>`: hàm nhận `ServerRequest` và trả `ServerResponse`. Handler định nghĩa **cách xử lý**.

Cơ chế dispatch:

~~~text
HttpServletRequest
    -> RouterFunctionMapping
    -> RouterFunction thử RequestPredicate
    -> HandlerFunction được chọn
    -> HandlerFunctionAdapter
    -> HandlerFunction.handle(ServerRequest)
    -> ServerResponse
~~~

Các phần quan trọng:

1. `RouterFunctionMapping` tự phát hiện các bean kiểu `RouterFunction<?>` được Spring quản lý, kết hợp chúng và kiểm tra request.
2. `HandlerFunctionAdapter` thực thi handler được router chọn. Nó không gọi method `@GetMapping`.
3. `RouterFunctions.route()` tạo builder để khai báo `GET`, `POST` và các predicate.
4. `ServerRequest` hỗ trợ đọc query parameter, header, path variable, body, v.v.; `ServerResponse` tạo status, header và body.
5. Router function có thể dùng bean/service Spring bình thường qua dependency injection.

Ví dụ fragment định nghĩa một route:

~~~java
@Bean
RouterFunction<ServerResponse> functionalRoutes() {
    return RouterFunctions.route()
        .GET("/fn/hello",
            request -> ServerResponse.ok().body("hello functional"))
        .build();
}
~~~

Đây là method cần đặt trong một `@Configuration` class với import tương ứng. Không dùng các class cùng tên dưới package `org.springframework.web.reactive.function.server`: đó là **WebFlux.fn**, chạy theo stack reactive khác.

### Thứ tự match trong một RouterFunction

Điểm khác với annotated controller là **router chức năng được duyệt theo thứ tự khai báo**. Khi route đầu match, route sau không được dùng. Do đó, đặt path cụ thể trước path tổng quát:

~~~java
@Bean
RouterFunction<ServerResponse> catalogRoutes() {
    return RouterFunctions.route()
        .GET("/catalog/special", request ->
            ServerResponse.ok().body("special"))
        .GET("/catalog/{slug}", request ->
            ServerResponse.ok().body(request.pathVariable("slug")))
        .build();
}
~~~

Nếu hoán đổi hai dòng `GET` trong ví dụ, path tổng quát `/catalog/{slug}` có thể bắt mất request `/catalog/special`. Trong ví dụ này, cả hai đoạn là **code minh họa** cần đặt vào class có `@Configuration` và import.

Với nhiều bean `RouterFunction`, việc chúng được sắp xếp/kết hợp cũng có ý nghĩa. Nếu thứ tự là yêu cầu nghiệp vụ, hãy viết một router rõ ràng hoặc sắp xếp bean có chủ đích và có integration test cho route chồng lấp.

## 5. Một project Spring Boot chứa cả hai mô hình, chạy được

Ví dụ dùng **Spring Boot 3.5.0**, **Java 17**, Maven và `spring-boot-starter-web`. Hai endpoint có chung service nhưng **đường dẫn riêng**, nên không cạnh tranh một URL:

- Annotated: `GET /api/annotated/hello?name=Lan`.
- Functional: `GET /api/functional/hello?name=Lan`.
- Functional có path variable: `GET /api/functional/items/42`.

Cấu trúc thư mục:

~~~text
handler-mapping-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/mappingdemo/
    MappingDemoApplication.java
    GreetingService.java
    AnnotatedGreetingController.java
    FunctionalGreetingHandler.java
    FunctionalRoutes.java
  src/test/java/com/example/mappingdemo/
    RoutingIntegrationTest.java
~~~

### 5.1. Maven POM

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>handler-mapping-demo</artifactId>
    <version>1.0.0</version>
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

Starter Web đưa Spring MVC, embedded Tomcat và những message converter phổ biến vào classpath. **Không cần thêm starter WebFlux** để dùng WebMvc.fn.

`src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

### 5.2. Entry point và service dùng chung

`src/main/java/com/example/mappingdemo/MappingDemoApplication.java`:

~~~java
package com.example.mappingdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MappingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MappingDemoApplication.class, args);
    }
}
~~~

`src/main/java/com/example/mappingdemo/GreetingService.java`:

~~~java
package com.example.mappingdemo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

### 5.3. Annotation-based controller

`src/main/java/com/example/mappingdemo/AnnotatedGreetingController.java`:

~~~java
package com.example.mappingdemo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/annotated")
public class AnnotatedGreetingController {

    private final GreetingService greetingService;

    public AnnotatedGreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping(
        path = "/hello",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String hello(
            @RequestParam(name = "name", defaultValue = "world")
            String name) {
        return greetingService.greet(name);
    }
}
~~~

`RequestMappingHandlerMapping` tìm mapping `GET /api/annotated/hello`. `RequestMappingHandlerAdapter` xử lý tham số `name` và gọi method Java. Giá trị trả về `String` của `@RestController` được ghi làm response body, không phải tên view.

### 5.4. Functional handler

`src/main/java/com/example/mappingdemo/FunctionalGreetingHandler.java`:

~~~java
package com.example.mappingdemo;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class FunctionalGreetingHandler {

    private final GreetingService greetingService;

    public FunctionalGreetingHandler(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    public ServerResponse hello(ServerRequest request) {
        String name = request.param("name")
                .filter(value -> !value.isBlank())
                .orElse("world");

        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body(greetingService.greet(name));
    }

    public ServerResponse item(ServerRequest request) {
        String id = request.pathVariable("id");

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ItemView(id, "functional"));
    }

    public record ItemView(String id, String source) {
    }
}
~~~

Method `hello` đọc query parameter trực tiếp từ `ServerRequest`; method `item` đọc path variable. Trong WebMvc.fn, các bước đọc parameter, validation và tạo `ServerResponse` thường được viết rõ trong handler hoặc helper; không tự động mang toàn bộ cơ chế `@RequestParam`/`@RequestBody` lên một `HandlerFunction` như cách Spring gọi method annotation.

### 5.5. RouterFunction: định tuyến functional endpoint

`src/main/java/com/example/mappingdemo/FunctionalRoutes.java`:

~~~java
package com.example.mappingdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@Configuration
public class FunctionalRoutes {

    @Bean
    public RouterFunction<ServerResponse> routes(
            FunctionalGreetingHandler handler) {

        return RouterFunctions.route()
                .GET("/api/functional/hello", handler::hello)
                .GET("/api/functional/items/{id}", handler::item)
                .build();
    }
}
~~~

Khi `RouterFunction<ServerResponse>` là Spring bean, `RouterFunctionMapping` có thể tự phát hiện. Khi incoming request match một predicate, Spring lấy `HandlerFunction` tương ứng; `HandlerFunctionAdapter` thực thi method `hello` hoặc `item`. Hai endpoint functional không cần `@RestController` và cũng không được xử lý bởi `RequestMappingHandlerMapping`.

## 6. Chạy, gửi request và kiểm tra output

Từ thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Hoặc:

~~~bash
mvn clean package
java -jar target/handler-mapping-demo-1.0.0.jar
~~~

Các lệnh sau giả định ứng dụng chạy thành công tại `localhost:8080`.

### Endpoint annotation

~~~bash
curl -i "http://localhost:8080/api/annotated/hello?name=Lan"
~~~

Response body chính xác:

~~~text
Hello, Lan
~~~

### Endpoint chức năng

~~~bash
curl -i "http://localhost:8080/api/functional/hello?name=Lan"
~~~

Response body chính xác cũng là:

~~~text
Hello, Lan
~~~

### Endpoint chức năng có path variable

~~~bash
curl -i "http://localhost:8080/api/functional/items/42"
~~~

Response JSON có hai thuộc tính:

~~~json
{
  "id": "42",
  "source": "functional"
}
~~~

Thứ tự key, khoảng trắng và các HTTP header phụ thuộc converter và cấu hình; hai trường JSON mới là hợp đồng được minh họa. Với `curl -i`, console còn hiển thị status line và headers trước body. Những body trên là kết quả do chính source code ví dụ tạo ra.

### Phân biệt GET, POST, Accept

~~~bash
curl -i -X POST "http://localhost:8080/api/annotated/hello"
curl -i -H "Accept: application/json" \
  "http://localhost:8080/api/annotated/hello"
~~~

Trong app ví dụ, annotated handler chỉ chấp nhận GET và sản xuất `text/plain`, nên request sai method hoặc điều kiện `Accept` có thể cho status 405 hoặc 406. Trạng thái của endpoint functional khi predicate không match có thể khác; không mặc định mọi lỗi HTTP method ở functional route đều tự động thành 405. Hãy kiểm tra HTTP response trên ứng dụng thật.

## 7. Kiểm thử tích hợp HTTP thật cho cả hai HandlerMapping

Thêm `src/test/java/com/example/mappingdemo/RoutingIntegrationTest.java`:

~~~java
package com.example.mappingdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RoutingIntegrationTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newHttpClient();

    private HttpResponse<String> get(String path) throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + path);
        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void annotatedControllerIsMapped() throws Exception {
        assertTrue(port > 0);
        HttpResponse<String> response =
                get("/api/annotated/hello?name=Lan");

        assertEquals(200, response.statusCode());
        assertEquals("Hello, Lan", response.body());
    }

    @Test
    void functionalHandlerIsMapped() throws Exception {
        HttpResponse<String> response =
                get("/api/functional/hello?name=Lan");

        assertEquals(200, response.statusCode());
        assertEquals("Hello, Lan", response.body());
    }

    @Test
    void unknownPathIsNotAnEndpoint() throws Exception {
        HttpResponse<String> response = get("/missing-endpoint");

        assertEquals(404, response.statusCode());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

`RANDOM_PORT` mở web server thật trên cổng OS cấp; `@LocalServerPort` đọc cổng được chọn. Bài test kiểm tra cả annotation route và functional route qua network nên xác nhận được rằng `DispatcherServlet` đã hoạt động với hai loại mapping. Bài test 404 chỉ có ý nghĩa khi ứng dụng không đăng ký route tĩnh/fallback nào bắt `/missing-endpoint`.

Có thể dùng `MockMvc` cho phần lớn unit/integration test MVC; tuy nhiên, phép kiểm HTTP thật hữu ích khi muốn xác nhận đầy đủ servlet registration, filter chain và server configuration.

## 8. Khi nào chọn @RestController, khi nào chọn WebMvc.fn?

Cả hai đều là mô hình chính thức của Spring MVC. Việc chọn nên dựa vào mức độ phù hợp với codebase, team và loại API, không vì một mô hình luôn nhanh hơn trong mọi trường hợp.

| Tiêu chí | Annotated controller | WebMvc.fn / handler chức năng |
|---|---|---|
| Khai báo route | `@RequestMapping`, `@GetMapping` trên method | `RouterFunction` và `RequestPredicate` |
| Handler thực thi | `HandlerMethod`, adapter phản chiếu method | `HandlerFunction` nhận `ServerRequest` |
| Tổ chức code | Class/controller với annotation | Router và handler có thể tách riêng |
| Binding tham số | Nhiều annotation như `@PathVariable`, `@RequestBody`, `@Valid` | Đọc và chuyển đổi từ `ServerRequest`, cần xử lý rõ ở handler |
| Xây response | Java return value, `ResponseEntity`, annotation | `ServerResponse` builder |
| Thứ tự route | Chọn mapping cụ thể nhất trong nhóm annotation | Duyệt route theo thứ tự khai báo |
| Cấu trúc chương trình | Phù hợp CRUD REST, controller/service phổ biến | Phù hợp router tường minh, DSL, endpoint nhỏ, composition |
| Chạy trên Servlet | Có | Có, cùng `DispatcherServlet` |
| Spring WebFlux bắt buộc? | Không | Không |
| Test | MockMvc, integration test | MockMvc, RouterFunction test và integration test |

**Ưu tiên annotated controller** khi project đã dùng controller/service layer, cần annotation binding và validation nhiều, hoặc team quen cơ chế `@RestControllerAdvice`, OpenAPI/validation trên method và cấu trúc controller.

**Chọn WebMvc.fn** khi muốn router tường minh, nhóm route theo chức năng, kết hợp predicate một cách linh hoạt, viết handler testable bằng request/response kiểu chức năng hoặc đang xây một lớp HTTP adapter mỏng.

**Có thể phối hợp cả hai** trong cùng Spring Boot MVC app. Khi phối hợp, phải đặt URL rõ ràng và quy ước trách nhiệm để tránh route collision, xác định chính xác handler nào xử lý từng URL.

## 9. Xử lý validation, exception, cross-cutting concern khác nhau thế nào?

### 9.1. Data binding và validation

Annotated controller hỗ trợ những kiểu thường dùng:

~~~java
@PostMapping(
    path = "/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<OrderResult> create(
        @Valid @RequestBody CreateOrderCommand command) {
    return ResponseEntity.ok(service.create(command));
}
~~~

Đây là **fragment** nằm trong controller đã có `service`, DTO và import thích hợp. Spring MVC có thể deserialize body vào DTO và gọi Bean Validation khi cấu hình phù hợp.

Trong WebMvc.fn, handler thường đọc body rõ ràng:

~~~java
public ServerResponse create(ServerRequest request) throws Exception {
    CreateOrderCommand command =
            request.body(CreateOrderCommand.class);

    OrderResult result = service.create(command);

    return ServerResponse.ok().body(result);
}
~~~

Đây cũng là **fragment** phụ thuộc các kiểu `CreateOrderCommand`, `OrderResult` và `service`. Handler cần kiểm tra dữ liệu/validation bằng cách phù hợp; không mặc định `@Valid` trên tham số functional handler được xử lý giống annotated controller. Với API nghiêm ngặt, hãy xác thực nội dung body, định dạng, business rule và trả lỗi có cấu trúc.

### 9.2. Exception và HTTP status

Với annotated controller, exception có thể được xử lý bởi `@ExceptionHandler`, `@RestControllerAdvice`, `ResponseStatusException` và chuỗi `HandlerExceptionResolver` của MVC.

Với functional handler, nên xử lý/trả `ServerResponse` lỗi rõ ràng và kiểm tra exception behavior thực tế. WebMvc.fn cung cấp các cách áp dụng handler hoặc filter chức năng, nhưng phạm vi xử lý có thể khác annotation controller. Đừng giả định rằng mọi `@ExceptionHandler` gắn ở controller annotation đều áp dụng cho mọi `HandlerFunction`. Sử dụng error contract nhất quán và test lỗi cho cả hai mô hình.

### 9.3. Filter, interceptor và Spring Security

- **Servlet Filter** nằm ngoài `DispatcherServlet`: có thể tác động đến cả annotated và functional endpoint nếu URL của chúng thuộc filter mapping.
- **HandlerInterceptor** chạy trong MVC dispatch; có thể gắn cùng các mapping tùy cấu hình interceptor và path pattern. Interceptor không phải là thay thế mặc định cho authentication/authorization tại Spring Security.
- **Spring Security FilterChain** được áp dụng tại tầng filter; điều kiện bảo vệ endpoint cần được test dựa trên URL và HTTP method thực tế.
- **Functional filter** trong RouterFunction là một abstraction khác Servlet Filter; thường chỉ áp dụng cho nhánh router tương ứng.

Đừng tách hoặc bỏ kiểm tra bảo mật chỉ vì thay một controller annotation thành functional route.

## 10. Mức độ ưu tiên khi có xung đột route

Giả sử bạn cố tình đăng ký cả hai mapping cho `GET /api/status`:

~~~java
// Annotation controller
@GetMapping("/api/status")
public String status() {
    return "annotated";
}
~~~

~~~java
// Trong RouterFunction bean
.GET("/api/status",
    request -> ServerResponse.ok().body("functional"))
~~~

Trong cấu hình chuẩn Spring MVC 6.2, `RouterFunctionMapping` có order -1 và `RequestMappingHandlerMapping` có order 0; vì vậy functional route có thể được chọn trước. Hai đoạn trên là **fragment minh họa xung đột**, không nằm trong project chạy ở mục 5.

Nguyên tắc xử lý:

1. Không đăng ký hai handler cho cùng **method, path và request conditions**.
2. Khi chuyển API từ annotation sang function, gỡ route cũ hoặc thay URL rõ ràng.
3. Nếu có một fallback router dạng wildcard, đưa các route cụ thể lên trước trong cùng router; kiểm tra xem fallback có chiếm route của annotation hay static resource không.
4. Với custom `HandlerMapping`, đọc cấu hình `order` thực tế thay vì dựa vào thứ tự suy đoán.
5. Viết regression test cho URL mà nhiều mapping có thể nhận.

**Lưu ý:** đối với **hai method annotation** trùng mapping, `RequestMappingHandlerMapping` có thể báo ambiguous mapping ngay khi startup; đối với **annotation + functional route**, chúng được đăng ký qua hai `HandlerMapping` khác nhau, nên không nhất thiết có cùng kiểu lỗi startup. Đây là lý do route collision xuyên mô hình có thể khó phát hiện hơn.

## 11. Chẩn đoán HandlerMapping khi endpoint không đúng kỳ vọng

### 11.1. Trước tiên đọc HTTP method, path và header thật

Một request có thể không khớp vì:

- `GET` so với `POST`;
- context path hoặc servlet path (`server.servlet.context-path`, `spring.mvc.servlet.path`);
- controller class mapping + method mapping;
- path variable, trailing slash hoặc pattern không khớp;
- `Content-Type` không phù hợp `consumes`;
- `Accept` không phù hợp `produces`;
- bean handler không nằm trong component scan;
- `RouterFunction` không đăng ký thành Spring bean;
- router tổng quát match trước router cụ thể;
- custom `HandlerMapping` chạy trước mapping dự kiến.

### 11.2. Actuator mappings endpoint

Khi project có **`spring-boot-starter-actuator`** và cho phép expose endpoint, `GET /actuator/mappings` có thể giúp xem các request mapping đang được ứng dụng đăng ký.

Ví dụ cấu hình trong môi trường phát triển:

~~~properties
management.endpoints.web.exposure.include=health,info,mappings
~~~

Gọi:

~~~bash
curl http://localhost:8080/actuator/mappings
~~~

**Chú ý:** project Maven ở mục 5 chỉ có `spring-boot-starter-web` và `spring-boot-starter-test`. Muốn chạy được endpoint này, phải thêm `spring-boot-starter-actuator`; nếu không, `/actuator/mappings` không tồn tại. Mappings endpoint có thể lộ cấu trúc URL/handler; chỉ expose khi có chính sách bảo vệ phù hợp.

### 11.3. Logging phục vụ chẩn đoán

Trong môi trường phát triển, có thể tăng logging tạm thời:

~~~properties
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.servlet.function.support.RouterFunctionMapping=TRACE
~~~

Các tên logger và mức chi tiết có thể khác theo phiên bản/framework code path; nên đối chiếu log thực tế. Không bật TRACE HTTP không kiểm soát trong production vì có thể tạo log lớn và lộ metadata request.

Nếu cần kiểm tra bean `HandlerMapping` và `order` mà không tự dò toàn bộ hệ thống, trong một test phát triển có thể inject danh sách `HandlerMapping`, sort theo `AnnotationAwareOrderComparator` và in class/order của các mapping. Từ đó xác nhận custom mapping có thay đổi thứ tự tiêu chuẩn hay không.

### 11.4. Phân loại lỗi

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| 404 | Không có handler nào match; prefix hoặc router bean sai | Kiểm tra method, URL, context/servlet path và bean |
| 405 | URL annotation match nhưng method sai | Kiểm tra `@GetMapping`/`@PostMapping` và client method |
| 406 | `Accept` không tương thích `produces` | Sửa điều kiện media type hoặc header |
| 415 | `Content-Type` không tương thích `consumes` | Đổi request body format hoặc contract |
| Ambiguous mapping khi startup | Hai annotated methods có mapping không phân biệt được | Sửa URL hoặc request conditions |
| Functional handler lấn annotation | RouterFunctionMapping có order sớm hơn | Loại route trùng, đổi path hoặc chỉnh route design |
| `@RestController` không hoạt động | Không được component scan hoặc thiếu Spring MVC setup | Kiểm tra package, annotation, starter |
| Functional route không xuất hiện | RouterFunction bean không đăng ký hoặc import WebFlux.fn | Kiểm tra bean type và package `web.servlet.function` |
| Handler được chọn nhưng lỗi convert response | Lỗi adapter/converter/serialization | Kiểm tra content type, DTO, exception |
| Test đơn lẻ pass, app thật lỗi | Thiếu filter/servlet mapping trong test | Bổ sung integration test HTTP thật |

## 12. Các phương thức mở rộng và giới hạn cần biết

### Tùy chỉnh HandlerMapping

Có thể tự viết một `HandlerMapping` hoặc đăng ký handler qua `WebMvcConfigurer` và cơ chế MVC cấu hình sẵn. Đây là nhu cầu nâng cao, ví dụ hệ thống plugin hoặc URL routing động.

Khi thực hiện phải quyết định rõ:

- `HandlerMapping` nhận những URL nào và chạy với `order` bao nhiêu;
- kiểu handler trả về sẽ được `HandlerAdapter` nào hỗ trợ;
- interceptor, security và exception được áp dụng ra sao;
- cách xử lý fallback, static resource, content negotiation;
- cách test để custom mapping không che mất route hiện hữu.

Chỉ trả về một object từ custom mapping **không đủ**; DispatcherServlet cần `HandlerAdapter.supports(handler)` tìm được adapter tương thích. Nếu không, request có thể lỗi dù bước mapping có handler.

### Static resources và view controller cũng dùng HandlerMapping

Không phải mapping nào cũng trỏ đến method `@Controller`. URL có thể phục vụ resource, chuyển hướng, forward view hoặc functional handler. Đây là nguyên nhân `/api/unknown` đôi khi được xử lý bởi resource handler rồi mới trả 404; kết luận chỉ dựa trên một dòng “No mapping” là chưa đủ nếu project có cấu hình resource/fallback riêng.

### So sánh với WebFlux

WebFlux sử dụng `DispatcherHandler` và các abstraction tương tự về ý tưởng nhưng thuộc **reactive stack**. WebFlux.fn dùng `org.springframework.web.reactive.function.server.*`; WebMvc.fn dùng `org.springframework.web.servlet.function.*`. Hai package không thay thế trực tiếp cho nhau. Nếu thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường ưu tiên chọn MVC Servlet theo quy tắc xác định web application type.

## 13. Checklist thiết kế và kiểm thử HandlerMapping

1. Xác định đúng **runtime Spring MVC** và DispatcherServlet mapping.
2. Chọn annotated controller hoặc WebMvc.fn cho từng nhóm API dựa trên cách xử lý request, validation và quy ước code.
3. Đặt URL và HTTP method rõ ràng; tránh trùng route giữa hai mô hình.
4. Với annotated handler, dùng điều kiện `method/path/params/headers/consumes/produces` tường minh.
5. Với functional routes, đặt route **cụ thể trước route tổng quát**, lưu RouterFunction thành bean và tách xử lý nghiệp vụ sang service.
6. Khi custom thứ tự, kiểm tra `HandlerMapping.order` và adapter tương thích.
7. Kiểm thử kết quả thành công, 404/405/406/415, validation, lỗi nghiệp vụ và quyền truy cập theo từng mô hình có dùng.
8. Kiểm thử HTTP thật hoặc MockMvc tương ứng; tránh phụ thuộc riêng vào log startup để kết luận routing đúng.
9. Nếu cần quan sát route, dùng Actuator mappings trong môi trường được kiểm soát hoặc log phù hợp.
10. Sau thay đổi, kiểm tra không làm ảnh hưởng static resources, actuator endpoints, security filters, path prefixes và fallback routes.

## Tài liệu chính thức

- [Spring Framework 6.2 — DispatcherServlet](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html): quy trình dispatch và chiến lược xử lý.
- [Spring Framework 6.2 — Annotated Controllers: Mapping Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html): điều kiện request mapping.
- [Spring Framework 6.2 — Functional Endpoints (WebMvc.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): RouterFunction, HandlerFunction, route order, ServerRequest/ServerResponse.
- [Spring Framework 6.2 — WebMvcConfigurationSupport Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurationSupport.html): HandlerMappings/HandlerAdapters và order tiêu biểu.
- [Spring Boot 3.5 — Actuator mappings](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/mappings.html): xem mapping tại runtime.

**Kết luận thực hành:** `HandlerMapping` quyết định request vào handler nào; `HandlerAdapter` giúp gọi đúng loại handler. `@RestController` dùng `RequestMappingHandlerMapping` và `RequestMappingHandlerAdapter`, còn WebMvc.fn dùng `RouterFunctionMapping` và `HandlerFunctionAdapter`. Cả hai chạy trên Spring MVC `DispatcherServlet`, có thể cùng tồn tại nhưng phải tránh route xung đột và kiểm thử đường dẫn thật.

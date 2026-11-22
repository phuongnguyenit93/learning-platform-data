# Kết hợp Controller và router chức năng trong cùng một ứng dụng Spring Boot

> **Phạm vi:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**. Chủ đề chính là **định tuyến web khi sử dụng đồng thời Controller có annotation và router chức năng** trong **một Spring MVC application**, không phải yêu cầu tạo hai server riêng. Bài cũng có ví dụ WebFlux độc lập để phân biệt đúng stack và package. Ví dụ Maven dùng Spring Boot **3.5.0** và JDK **17**.

## 1. Có thể trộn hai mô hình routing trong cùng ứng dụng không?

**Có.** Một ứng dụng Spring Boot MVC có thể khai báo:

- Controller theo annotation, ví dụ `@RestController` với `@GetMapping`, `@PostMapping` và `@RequestMapping`.
- Bean `RouterFunction<ServerResponse>` của **WebMvc.fn**, dùng `RouterFunctions.route()` và `HandlerFunction` để khai báo endpoint chức năng.

Hai mô hình dùng chung **ApplicationContext**, bean/service, dependency injection, embedded Servlet server và một `DispatcherServlet`. Chúng không cần mở cổng riêng. Spring MVC có `HandlerMapping` và `HandlerAdapter` chuyên biệt để DispatcherServlet nhận diện và thực thi từng dạng handler.

Ví dụ cùng server `localhost:8080`:

~~~text
GET /api/annotated/hello?name=Lan
    -> @RestController -> GreetingService -> JSON

GET /api/functional/hello?name=Lan
    -> RouterFunction -> FunctionalApiHandler
    -> GreetingService -> JSON
~~~

Controller và functional handler có thể trả **cùng contract JSON** nhưng khác cách khai báo và bind request.

Điều quan trọng là chọn **đúng package**:

| Thành phần | Spring MVC / Servlet | Spring WebFlux / reactive |
|---|---|---|
| Starter | `spring-boot-starter-web` | `spring-boot-starter-webflux` |
| Front controller | `DispatcherServlet` | `DispatcherHandler` |
| RouterFunction | `org.springframework.web.servlet.function.RouterFunction` | `org.springframework.web.reactive.function.server.RouterFunction` |
| ServerRequest | `org.springframework.web.servlet.function.ServerRequest` | `org.springframework.web.reactive.function.server.ServerRequest` |
| ServerResponse | `org.springframework.web.servlet.function.ServerResponse` | `org.springframework.web.reactive.function.server.ServerResponse` |
| Functional handler return | `ServerResponse` (đồng bộ từ góc nhìn API) | `Mono<ServerResponse>` |
| Annotation controller | `@RestController` | `@RestController` cũng dùng được |

**Không import WebFlux.fn vào Spring MVC chỉ vì cả hai cùng có kiểu `RouterFunction`.** Hai package có tên type giống nhau nhưng framework nhận diện và dispatch theo runtime stack khác nhau.

## 2. Luồng HTTP của Spring MVC khi có hai kiểu handler

Một HTTP request qua Spring MVC có luồng khái quát:

~~~text
HTTP request
     |
     v
Servlet container (ví dụ embedded Tomcat)
     |
     v
Servlet Filter chain (Spring Security nếu có)
     |
     v
DispatcherServlet
     |
     +--- HandlerMapping theo thứ tự
     |       |
     |       +-- RouterFunctionMapping
     |       |       +-- khớp RouterFunction?
     |       |
     |       +-- RequestMappingHandlerMapping
     |               +-- khớp @GetMapping/@PostMapping?
     |
     +--- handler được chọn
     |       |
     |       +-- HandlerFunction (WebMvc.fn)
     |       |       -> HandlerFunctionAdapter
     |       |
     |       +-- HandlerMethod (Controller)
     |               -> RequestMappingHandlerAdapter
     |
     +--- tạo ServerResponse/response body/view
     +--- exception resolution/interceptors phù hợp
     |
     v
HTTP response
~~~

Đây là sơ đồ rút gọn; thứ tự thực tế còn có static resource mapping, view controller, custom mappings, multipart processing và async flow.

### 2.1. Annotated Controller đi qua gì?

`RequestMappingHandlerMapping` tạo và tìm mapping cho các method có annotation: `@GetMapping`, `@PostMapping`, `@RequestMapping`, v.v. Khi tìm được method thích hợp, nó trả `HandlerMethod`.

`RequestMappingHandlerAdapter` thực thi method đó, hỗ trợ argument resolver cho `@PathVariable`, `@RequestParam`, `@RequestBody`, `@RequestHeader`, validation và return-value handlers. Spring MVC có thể dùng `HttpMessageConverter` để serialize JSON.

Ví dụ:

~~~java
@GetMapping("/api/annotated/hello")
public Greeting hello(@RequestParam String name) {
    return service.greet(name, "annotated");
}
~~~

Đây là **fragment trong một @RestController**, không phải Java file độc lập; `Greeting` và `service` là kiểu/bean cần được định nghĩa.

### 2.2. WebMvc.fn đi qua gì?

`RouterFunctionMapping` tìm các `RouterFunction<?>` bean, thử `RequestPredicate` của chúng và lấy ra `HandlerFunction` phù hợp. `HandlerFunctionAdapter` gọi handler để tạo `ServerResponse`.

Ví dụ một fragment:

~~~java
@Bean
RouterFunction<ServerResponse> routes(MyHandler handler) {
    return RouterFunctions.route()
        .GET("/api/functional/hello", handler::hello)
        .build();
}
~~~

Method trên thuộc một configuration class, cần các import từ **`org.springframework.web.servlet.function`**. `MyHandler.hello` phải có kiểu tương thích như `ServerResponse hello(ServerRequest request)`.

**Không cần `@EnableWebMvc`.** Với Spring Boot Web starter thông thường, các bean hạ tầng WebMvc.fn đã được cấu hình. Gắn `@EnableWebMvc` chỉ để có functional router là việc không cần thiết và có thể thay đổi Boot MVC auto-configuration.

## 3. Điểm chung và khác giữa hai mô hình

| Khía cạnh | Annotation Controller | WebMvc.fn |
|---|---|---|
| Định nghĩa đường dẫn | `@GetMapping`, `@PostMapping`, class-level `@RequestMapping` | `RouterFunctions.route().GET(...).POST(...)` |
| Code xử lý | Method trên bean `@Controller`/`@RestController` | `HandlerFunction<ServerResponse>` nhận `ServerRequest` |
| Bind request | Annotation-based argument resolvers | Đọc `ServerRequest` bằng API tường minh |
| Tạo response | Return POJO, `ResponseEntity`, view, v.v. | `ServerResponse.ok()/status()/body(...)` |
| Chia logic | Controller gọi bean service/repository | Functional handler gọi cùng bean service/repository |
| Tìm handler | `RequestMappingHandlerMapping` | `RouterFunctionMapping` |
| Thực thi | `RequestMappingHandlerAdapter` | `HandlerFunctionAdapter` |
| Route order | Trong cùng annotated mapping: chọn điều kiện cụ thể nhất | Functional routes được xét theo **thứ tự khai báo** |
| Cross-cutting | Servlet Filter, HandlerInterceptor, controller advice tùy cơ chế | Servlet Filter, HandlerInterceptor, router filter và xử lý lỗi phù hợp |
| Chạy trên server | Servlet container | Cùng Servlet container |
| Có cần WebFlux? | Không | Không |

Hai mô hình không bắt buộc dùng chung một cách bind tham số. Điều nên chia sẻ là **business service, domain model, validation contract, serialization contract và chính sách bảo mật**.

### 3.1. Vì sao chọn phối hợp?

Các tình huống hợp lý:

1. Một project có nhiều REST controllers đang chạy tốt, nhưng muốn thêm một nhóm endpoint nhỏ với router DSL rõ ràng.
2. Một module tích hợp plugin tự cung cấp `RouterFunction` bean; phần API nghiệp vụ chính vẫn dùng controllers.
3. Chuyển đổi tăng dần từ functional route sang annotations hoặc ngược lại mà không viết lại service/repository.
4. Một số endpoint cần composition theo predicate, còn các REST CRUD cần annotation binding và validation tiện lợi.
5. Muốn nhóm một số route theo feature ở một router nhưng vẫn giữ các controller hiện hữu.

**Không phải** cứ dùng đồng thời là hiệu năng tăng. Hai kiểu handler tồn tại trên cùng nền tảng MVC; đo hiệu năng cần benchmark với workload thực và cấu hình tương đương.

## 4. Tránh xung đột URL giữa Controller và router chức năng

Đây là rủi ro lớn nhất khi “kết hợp”.

Trong cấu hình Spring MVC Framework 6.2 thông thường, `RouterFunctionMapping` có thứ tự ưu tiên nhỏ hơn `RequestMappingHandlerMapping` (thường **-1** so với **0**). DispatcherServlet duyệt theo order, và dừng ở `HandlerMapping` đầu tiên trả handler phù hợp.

Vì vậy, đoạn sau **nguy hiểm**:

~~~java
// Fragment trong @RestController:
@GetMapping("/api/status")
public String status() {
    return "annotated";
}
~~~

~~~java
// Fragment trong @Configuration:
@Bean
RouterFunction<ServerResponse> statusRoute() {
    return RouterFunctions.route()
        .GET("/api/status",
            request -> ServerResponse.ok().body("functional"))
        .build();
}
~~~

Ở thứ tự mặc định nói trên, functional route có thể được chọn trước; bạn không nên kỳ vọng method controller được gọi chỉ vì nó cũng khớp URL.

**Khác nhau giữa các kiểu xung đột:**

- Hai annotated controller method có cùng mapping/điều kiện thường bị phát hiện là **ambiguous mapping** khi đăng ký, có thể khiến startup thất bại.
- Một annotation route và một functional route nằm trong **hai HandlerMapping khác nhau**. Chúng không nhất thiết tạo cùng lỗi startup; một handler có thể lấn handler còn lại theo thứ tự.
- Hai functional routes có điều kiện chồng lấp: router xét **lần lượt từ trên xuống**, route match đầu có thể chiếm request của route sau.
- Custom `HandlerMapping` hoặc `@Order` có thể thay đổi hành vi so với cấu hình tiêu chuẩn.

**Chiến lược tránh collision:**

~~~text
/api/annotated/**   -> controllers
/api/functional/**  -> WebMvc.fn routers

hoặc

/api/users/**       -> UsersController
/api/reports/**     -> ReportsRouter
~~~

Không nhất thiết phải có tên `annotated`/`functional` trong production: dùng prefix theo **feature/domain** còn tốt hơn. Điều quan trọng là **quyền sở hữu route rõ ràng** và không có fallback quá rộng.

### 4.1. Router chức năng phải ưu tiên route cụ thể

Ví dụ thứ tự hợp lý:

~~~java
return RouterFunctions.route()
    .GET("/api/files/special",
         request -> ServerResponse.ok().body("special"))
    .GET("/api/files/{name}",
         request -> ServerResponse.ok()
             .body(request.pathVariable("name")))
    .build();
~~~

Nếu đảo thứ tự, `/api/files/{name}` có thể bắt luôn `/api/files/special`. Mô hình annotation thì chọn method theo độ cụ thể trong tập mapping annotation, không dựa vào thứ tự method xuất hiện trong file Java.

Cách an toàn nhất là viết test đối với các path giao nhau, không dựa vào suy luận bằng mắt.

## 5. Project Spring Boot MVC hoàn chỉnh chứa cả Controller và RouterFunction

Project này **độc lập, chạy được** với JDK 17+, Maven và Spring Boot 3.5.0. Nó dùng chung một service và DTO giữa hai mô hình.

Các URL:

~~~text
GET /api/annotated/hello?name=Lan
GET /api/functional/hello?name=Lan
GET /api/annotated/items/42
GET /api/functional/items/42
~~~

Tất cả chạy trong **một** process, một port và một `DispatcherServlet`.

### 5.1. Cấu trúc thư mục

~~~text
mixed-routing-mvc/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/mixedmvc/
    MixedMvcApplication.java
    GreetingPayload.java
    ItemPayload.java
    GreetingService.java
    AnnotatedApiController.java
    FunctionalApiHandler.java
    FunctionalRoutes.java
  src/test/java/com/example/mixedmvc/
    MixedRoutingIntegrationTest.java
~~~

### 5.2. Maven POM

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
    <artifactId>mixed-routing-mvc</artifactId>
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

**Chỉ cần `spring-boot-starter-web`**, không thêm `spring-boot-starter-webflux` để dùng WebMvc.fn. Maven parent quản lý dependency versions tương thích.

`src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

### 5.3. Entry point

`src/main/java/com/example/mixedmvc/MixedMvcApplication.java`:

~~~java
package com.example.mixedmvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MixedMvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(MixedMvcApplication.class, args);
    }
}
~~~

### 5.4. DTO và service chia sẻ

`src/main/java/com/example/mixedmvc/GreetingPayload.java`:

~~~java
package com.example.mixedmvc;

public record GreetingPayload(String message, String source) {
}
~~~

`src/main/java/com/example/mixedmvc/ItemPayload.java`:

~~~java
package com.example.mixedmvc;

public record ItemPayload(String id, String source) {
}
~~~

`src/main/java/com/example/mixedmvc/GreetingService.java`:

~~~java
package com.example.mixedmvc;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public GreetingPayload greet(String name, String source) {
        return new GreetingPayload("Hello, " + name, source);
    }

    public ItemPayload findItem(String id, String source) {
        return new ItemPayload(id, source);
    }
}
~~~

Hai record là Java 17. Trong ứng dụng thật, service có thể gọi repository và domain rules, còn controller/router handler chỉ làm HTTP adapter. Biến `source` ở đây chỉ để quan sát handler nào chạy trong demo; không phải thiết kế domain bắt buộc.

### 5.5. Controller theo annotation

`src/main/java/com/example/mixedmvc/AnnotatedApiController.java`:

~~~java
package com.example.mixedmvc;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/annotated")
public class AnnotatedApiController {

    private final GreetingService service;

    public AnnotatedApiController(GreetingService service) {
        this.service = service;
    }

    @GetMapping(
        path = "/hello",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public GreetingPayload hello(
            @RequestParam(name = "name", defaultValue = "world")
            String name) {
        return service.greet(name, "annotated");
    }

    @GetMapping(
        path = "/items/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ItemPayload item(@PathVariable String id) {
        return service.findItem(id, "annotated");
    }
}
~~~

Ở đây `@RequestMapping("/api/annotated")` là prefix cấp class, không phải Servlet context path. `@GetMapping` và `@PathVariable` được Spring MVC argument resolvers hỗ trợ. Response là DTO record, được JSON message converter serialize.

### 5.6. Functional handler dùng cùng service

`src/main/java/com/example/mixedmvc/FunctionalApiHandler.java`:

~~~java
package com.example.mixedmvc;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class FunctionalApiHandler {

    private final GreetingService service;

    public FunctionalApiHandler(GreetingService service) {
        this.service = service;
    }

    public ServerResponse hello(ServerRequest request) {
        String name = request.param("name")
                .filter(value -> !value.isBlank())
                .orElse("world");

        GreetingPayload body = service.greet(name, "functional");

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }

    public ServerResponse item(ServerRequest request) {
        String id = request.pathVariable("id");
        ItemPayload body = service.findItem(id, "functional");

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }
}
~~~

Đoạn code trên là **WebMvc.fn**, vì import `org.springframework.web.servlet.function.*`. Return type `ServerResponse` không phải `Mono<ServerResponse>`. Handler đọc query parameter bằng `request.param` và path variable bằng `request.pathVariable` rồi trả response qua `ServerResponse` builder.

### 5.7. Bean RouterFunction đăng ký hai URL mới

`src/main/java/com/example/mixedmvc/FunctionalRoutes.java`:

~~~java
package com.example.mixedmvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> apiRoutes(
            FunctionalApiHandler handler) {

        return RouterFunctions.route()
                .GET("/api/functional/hello", handler::hello)
                .GET("/api/functional/items/{id}", handler::item)
                .build();
    }
}
~~~

`@Bean` là điểm quan trọng: `RouterFunctionMapping` lấy các RouterFunction beans trong application context. Nếu bạn chỉ tạo router trong một local variable của method không được gọi/đăng ký, MVC không có cách tự biết nó.

Trong project mẫu:

- Spring Boot component-scan tất cả Java classes dưới `com.example.mixedmvc`.
- `GreetingService` là bean `@Service`.
- `AnnotatedApiController` là bean `@RestController`.
- `FunctionalApiHandler` là bean `@Component`.
- `FunctionalRoutes#apiRoutes` được tạo thành bean `RouterFunction<ServerResponse>`.
- DispatcherServlet có thể dispatch cả annotation và function endpoints.

Đây là **một project**, không phải hai server hoặc hai application context riêng.

## 6. Chạy một lần, truy cập cả hai kiểu endpoint

Trong thư mục có `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Hoặc đóng gói:

~~~bash
mvn clean package
java -jar target/mixed-routing-mvc-1.0.0.jar
~~~

Nếu cổng 8080 chưa bị chiếm, các request sau dùng cùng base URL.

### 6.1. Request vào annotated controller

~~~bash
curl -i "http://localhost:8080/api/annotated/hello?name=Lan"
~~~

HTTP body:

~~~json
{"message":"Hello, Lan","source":"annotated"}
~~~

### 6.2. Request vào functional handler

~~~bash
curl -i "http://localhost:8080/api/functional/hello?name=Lan"
~~~

HTTP body:

~~~json
{"message":"Hello, Lan","source":"functional"}
~~~

Hai endpoint xử lý bằng cùng `GreetingService.greet`, nhưng khác nhánh HTTP adapter. Thứ tự JSON properties phụ thuộc converter và cấu hình serialization; ở đây minh họa hai trường cần có, không yêu cầu kiểm thử bằng chuỗi JSON y hệt nếu đã tùy chỉnh mapper.

### 6.3. Path variable ở hai nhánh

~~~bash
curl -i http://localhost:8080/api/annotated/items/42
curl -i http://localhost:8080/api/functional/items/42
~~~

Body nhánh annotated:

~~~json
{"id":"42","source":"annotated"}
~~~

Body nhánh functional:

~~~json
{"id":"42","source":"functional"}
~~~

Với `curl -i`, console còn có status line và response headers. Mỗi endpoint thành công được kỳ vọng trả **HTTP 200** và JSON body tương ứng.

### 6.4. Endpoint không đăng ký

~~~bash
curl -i http://localhost:8080/api/unknown
~~~

Trong project mẫu không có route fallback cho `/api/unknown`, HTTP status thường là **404**. Trong app thật, static resource handlers hoặc custom router catch-all có thể làm đường xử lý lỗi khác đi.

## 7. Test tích hợp: chứng minh cả hai mô hình thật sự được đăng ký

Thêm `src/test/java/com/example/mixedmvc/MixedRoutingIntegrationTest.java`:

~~~java
package com.example.mixedmvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MixedRoutingIntegrationTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper mapper = new ObjectMapper();

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );
    }

    @Test
    void annotatedControllerIsAvailable() throws Exception {
        assertTrue(port > 0);
        HttpResponse<String> response =
                get("/api/annotated/hello?name=Lan");

        assertEquals(200, response.statusCode());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("Hello, Lan", body.get("message").asText());
        assertEquals("annotated", body.get("source").asText());
    }

    @Test
    void functionalRouterIsAvailable() throws Exception {
        HttpResponse<String> response =
                get("/api/functional/hello?name=Lan");

        assertEquals(200, response.statusCode());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("Hello, Lan", body.get("message").asText());
        assertEquals("functional", body.get("source").asText());
    }

    @Test
    void bothRoutesCanBindPathVariables() throws Exception {
        HttpResponse<String> annotated =
                get("/api/annotated/items/42");
        HttpResponse<String> functional =
                get("/api/functional/items/42");

        assertEquals(200, annotated.statusCode());
        assertEquals(200, functional.statusCode());

        JsonNode annotatedBody = mapper.readTree(annotated.body());
        JsonNode functionalBody = mapper.readTree(functional.body());

        assertEquals("42", annotatedBody.get("id").asText());
        assertEquals("42", functionalBody.get("id").asText());
        assertEquals("annotated", annotatedBody.get("source").asText());
        assertEquals("functional", functionalBody.get("source").asText());
    }

    @Test
    void unknownApiPathReturnsNotFound() throws Exception {
        assertEquals(404, get("/api/unknown").statusCode());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

`@SpringBootTest(RANDOM_PORT)` mở embedded server thật, không chỉ gọi trực tiếp Java methods. `@LocalServerPort` lấy cổng HTTP do hệ điều hành chọn, tránh đụng cổng 8080 trong CI.

Bài test xác nhận đồng thời:

- annotated endpoint có mặt;
- functional endpoint có mặt;
- cả hai cùng xử lý path variable;
- cùng JSON contract nhưng `source` thể hiện nhánh xử lý;
- URL không được đăng ký không vô tình trở thành fallback route.

`ObjectMapper` ở test được dùng để so JSON theo cấu trúc thay vì phụ thuộc thứ tự hai field, phù hợp khi serialization settings thay đổi.

**Giới hạn:** test này kiểm tra tính đúng của route và HTTP response, không benchmark performance, authentication hay xác minh thứ tự HandlerMapping khi cố tình tạo collision. Khi có collision, hãy thêm test chuyên biệt cho URL đó và kiểm tra `HandlerMapping` thực tế.

## 8. Khi nào cần WebMvc.fn router filter, khi nào dùng Servlet Filter?

Một router có thể gắn `HandlerFilterFunction` để xử lý trước/sau functional handler:

~~~java
@Bean
RouterFunction<ServerResponse> filteredRoutes(
        FunctionalApiHandler handler) {

    return RouterFunctions.route()
            .GET("/api/functional/hello", handler::hello)
            .filter((request, next) -> {
                // Hook chỉ dành cho nhánh router đang được build.
                return next.handle(request);
            })
            .build();
}
~~~

Đây là **fragment minh họa** và sẽ **trùng endpoint** với bean `apiRoutes` của project mẫu. Không thêm vào cùng lúc nếu chưa thay thế/di chuyển route tương ứng.

Khác biệt giữa các điểm mở rộng:

- **Router filter / HandlerFilterFunction:** gắn vào chuỗi router chức năng, không tự chạy trên mọi annotated controller.
- **Servlet Filter:** chạy ở tầng Servlet trước/sau DispatcherServlet, có thể áp dụng cho cả hai nhánh nếu filter mapping bao phủ URL tương ứng.
- **HandlerInterceptor:** hook trong MVC HandlerExecutionChain, phạm vi phụ thuộc cấu hình HandlerMapping và path patterns.
- **Spring Security servlet filter chain:** nơi quan trọng để kiểm soát xác thực và phân quyền dùng chung cho cả hai kiểu endpoint.

Nếu cần correlation ID hoặc security chung, đừng đặt logic bắt buộc chỉ trong functional router filter rồi quên các annotated endpoints. Cần chọn một tầng shared phù hợp và test toàn bộ URL.

## 9. Validation, JSON và xử lý lỗi khi trộn hai mô hình

### 9.1. Binding request khác nhau

Annotated controller có thể dùng:

~~~java
@PostMapping("/orders")
public ResponseEntity<OrderView> create(
        @Valid @RequestBody CreateOrderCommand command) {
    OrderView result = service.create(command);
    return ResponseEntity.ok(result);
}
~~~

Đây là **method fragment**, cần DTO, service, Bean Validation và imports thích hợp. `@Valid` trên argument controller được MVC hỗ trợ khi có Bean Validation provider phù hợp.

Functional handler dùng:

~~~java
public ServerResponse create(ServerRequest request)
        throws Exception {

    CreateOrderCommand command =
            request.body(CreateOrderCommand.class);

    // Validate command bằng validator/business rules thích hợp.
    OrderView result = service.create(command);

    return ServerResponse.ok().body(result);
}
~~~

Đây cũng là **fragment**, không nằm trong project chạy của mục 5. Nó thể hiện khác biệt: functional handler chủ động đọc body từ `ServerRequest`; không mặc nhiên nhận cùng các annotation-based argument resolvers như một controller method.

Nếu hai kiểu route cùng xử lý nghiệp vụ tạo order, nên chia sẻ **validator, service và error contract** để hai endpoint không trả 400/422/500 khác nhau một cách vô tình.

### 9.2. Exception handling

Với Controller, Spring MVC thường dùng `@ExceptionHandler`, `@ControllerAdvice` hoặc `@RestControllerAdvice` để chuẩn hóa lỗi.

Với WebMvc.fn, handler có thể trả `ServerResponse` lỗi trực tiếp, dùng router filter hoặc cơ chế `HandlerExceptionResolver` phù hợp. **Không giả định** mọi `@ExceptionHandler` thiết kế cho annotated controller sẽ tự áp dụng giống hệt cho functional handler.

Quy tắc an toàn:

1. Định nghĩa chuẩn body lỗi (mã, message, correlation ID, thời điểm nếu cần).
2. Tạo một policy trong tầng business/exception cho cả hai nhánh.
3. Viết test 400/404/403/500 theo những lỗi mà ứng dụng thực sự có.
4. Đảm bảo thông điệp lỗi không lộ stack trace hoặc dữ liệu nội bộ khi production.
5. Với JSON, xem xét cấu hình `HttpMessageConverter`/Jackson chung để không có hai định dạng response khác nhau.

### 9.3. Tránh nhầm HTTP method với “route được ưu tiên”

Ví dụ controller nhận `POST /api/orders` nhưng functional router có `GET /api/orders`. Chúng có thể bổ sung cho nhau nếu điều kiện matching tương thích; nhưng khi functional router có catch-all quá rộng hoặc fallback không xét HTTP method, một request có thể bị chọn sai nhánh.

Hãy khai báo đủ method, path, `Content-Type` và `Accept` khi cần. CORS preflight `OPTIONS` cũng cần được test nếu browser gọi API cross-origin.

## 10. Spring Security và CORS khi có cả hai kiểu endpoint

Với Spring MVC, cả annotated controller và WebMvc.fn đi qua **Servlet Filter chain**, bao gồm Spring Security khi đã thêm starter bảo mật. Vì vậy, route có annotation hay functional không tự quyết định một endpoint có public hay private.

Giả sử bạn có hai nhóm:

~~~text
/api/annotated/**  -> cần đăng nhập
/api/functional/** -> cũng cần đăng nhập
~~~

Nếu policy chỉ bảo vệ `/api/annotated/**` rồi cho phép mọi route khác, functional endpoints có thể bị lộ. Hãy thiết kế authorization theo business resource và deny-by-default nếu phù hợp, sau đó test đầy đủ:

- Anonymous gọi endpoint protected phải bị từ chối phù hợp (401 hoặc redirect login, tùy cấu hình).
- User đã xác thực nhưng thiếu quyền phải bị chặn (thường 403).
- User đủ quyền có thể gọi cả annotated và functional endpoint.
- `OPTIONS` preflight không bị chặn không đúng khi CORS đã cấu hình.
- Không có route wildcard/fallback nào làm lộ thông tin do bypass rule.

**CORS** trong Spring MVC có thể cấu hình bằng `WebMvcConfigurer#addCorsMappings` và `@CrossOrigin` ở controller khi phù hợp. Nhưng một số WebMvc.fn routes có cách áp dụng CORS, filters và request predicates riêng; hãy kiểm tra preflight cho cả hai nhánh. CORS chỉ kiểm soát quyền đọc response của browser, không thay thế authentication/authorization.

Với reactive WebFlux, security là `SecurityWebFilterChain`; đừng sao chép nguyên `SecurityFilterChain` của Servlet MVC.

## 11. Tác động của context path, servlet path và proxy

Router và controller cùng chạy sau Servlet context. Ví dụ:

~~~properties
server.servlet.context-path=/portal
~~~

Khi đó các URL trong project MVC chuyển thành:

~~~text
/portal/api/annotated/hello
/portal/api/functional/hello
~~~

Không thêm `/portal` vào `@RequestMapping` hoặc `RouterFunctions.GET(...)`, vì tiền tố context path do Servlet container quản lý.

Nếu cấu hình:

~~~properties
spring.mvc.servlet.path=/service
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Spring Boot 3.5 có caveat: Servlet prefix mapping qua `spring.mvc.servlet.path` không tương thích với `PathPatternParser` mặc định; chọn `ant-path-matcher` theo tài liệu Boot. Khi đó URL MVC có thể là `/service/api/annotated/hello` và `/service/api/functional/hello`, cộng thêm context path nếu có. **Bộ code mẫu ban đầu không cần property này.**

Đằng sau ingress/proxy, public URL còn có thể bị rewrite. Nếu browser gọi `https://example.com/v1/...` nhưng backend nhận `/api/...`, phải test đầy đủ đường dẫn ở cả hai phía thay vì nhầm rewrite với Servlet mapping.

## 12. Mở rộng thêm router mà vẫn giữ Controller: tổ chức dự án

Khi project tăng số lượng endpoint, có thể dùng cấu trúc feature-oriented:

~~~text
com.example.shop
  ShopApplication
  customers/
    CustomerController.java
    CustomerService.java
  reports/
    ReportHandler.java
    ReportRoutes.java
    ReportService.java
  inventory/
    InventoryController.java
    InventoryService.java
  shared/
    ErrorResponse.java
    SecurityConfig.java
~~~

Ý tưởng:

- Domain customers/inventory dùng annotated controllers vì cần DTO binding/validation.
- Domain reports dùng WebMvc.fn router cho một nhóm request predicates đặc thù.
- Mọi HTTP adapter gọi service/application layer phù hợp; không nhúng truy vấn DB trực tiếp vào router bean.
- Giữ bean registration trong phạm vi component scan của `@SpringBootApplication` hoặc import cấu hình rõ ràng.
- Có quy ước path ownership và API versioning: `/api/v1/customers`, `/api/v1/reports`.

**Không buộc một feature phải dùng đủ hai kiểu handler.** Chỉ dùng kết hợp khi có lợi ích rõ; nếu một controller đang đơn giản và dễ bảo trì, không cần chuyển qua functional router để tăng độ phức tạp.

### 12.1. Đăng ký nhiều RouterFunction bean

Có thể đăng ký nhiều bean kiểu `RouterFunction<ServerResponse>` để tách feature, ví dụ module reports và search. Spring kết hợp/router những bean đó theo cơ chế của `RouterFunctionMapping`.

Rủi ro: các bean có route chồng lấp. Thứ tự bean/router có thể ảnh hưởng handler nào chạy. Nếu order có ý nghĩa, cần quản lý rõ thứ tự và viết test; không dựa vào tên class hay thứ tự được filesystem liệt kê.

Với một feature có route cụ thể và fallback, dễ kiểm soát hơn nếu nhóm chúng vào **một router builder** và đặt route cụ thể trước route tổng quát.

### 12.2. Tránh tạo RouterFunction ngoài Spring context

Một số đoạn code chỉ chạy khi bạn gọi trực tiếp:

~~~java
RouterFunction<ServerResponse> localRouter =
        RouterFunctions.route()
            .GET("/local",
                request -> ServerResponse.ok().body("local"))
            .build();
~~~

Đây là **fragment trong method**: nếu `localRouter` không được trả từ một `@Bean` hoặc đăng ký dưới hình thức Spring quản lý, `RouterFunctionMapping` thông thường sẽ không tự nhận diện nó. Hãy đặt bean config vào class được component scan.

## 13. Khi nào kết hợp annotated Controller với WebFlux.fn?

Đây là **cách phối hợp thứ hai**, dành cho ứng dụng **REACTIVE** chứ không phải Spring MVC. Trong WebFlux, `@RestController` và `RouterFunction` thuộc package `org.springframework.web.reactive.function.server` chạy cùng `DispatcherHandler`.

Khác biệt quan trọng:

- Controller annotated có thể trả `Mono<T>` hoặc `Flux<T>`.
- Functional handler có method nhận `ServerRequest` và trả `Mono<ServerResponse>`.
- Reactor Netty là server embedded mặc định của `spring-boot-starter-webflux`.
- Cả hai cùng chạy trong một reactive app; không cần gắn thêm `spring-boot-starter-web`.
- Không đem WebMvc.fn types vào WebFlux project: dù tên generic trùng nhau, đó là hệ API khác.

### 13.1. Project WebFlux độc lập

Cấu trúc:

~~~text
mixed-routing-webflux/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/mixedflux/
    MixedFluxApplication.java
    ReactiveController.java
    ReactiveRoutes.java
~~~

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
    <artifactId>mixed-routing-webflux</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

`src/main/resources/application.properties`:

~~~properties
server.port=8081
~~~

`src/main/java/com/example/mixedflux/MixedFluxApplication.java`:

~~~java
package com.example.mixedflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MixedFluxApplication {
    public static void main(String[] args) {
        SpringApplication.run(MixedFluxApplication.class, args);
    }
}
~~~

`src/main/java/com/example/mixedflux/ReactiveController.java`:

~~~java
package com.example.mixedflux;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveController {

    @GetMapping(
        path = "/api/annotated/hello",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> hello() {
        return Mono.just("hello reactive annotated");
    }
}
~~~

`src/main/java/com/example/mixedflux/ReactiveRoutes.java`:

~~~java
package com.example.mixedflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class ReactiveRoutes {

    @Bean
    RouterFunction<ServerResponse> reactiveApiRoutes() {
        return RouterFunctions.route()
                .GET("/api/functional/hello",
                    request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .bodyValue("hello reactive functional"))
                .build();
    }
}
~~~

Chạy trong thư mục project WebFlux:

~~~bash
mvn spring-boot:run
~~~

Kiểm tra:

~~~bash
curl -i http://localhost:8081/api/annotated/hello
curl -i http://localhost:8081/api/functional/hello
~~~

Body dự kiến lần lượt:

~~~text
hello reactive annotated
~~~

và:

~~~text
hello reactive functional
~~~

Cả hai HTTP endpoints cùng chạy trên một **reactive server**. `ReactiveController.hello()` trả `Mono<String>`; functional handler mà router sử dụng trả `Mono<ServerResponse>` từ `ServerResponse.ok().bodyValue(...)`. Đây là khác biệt quan trọng với WebMvc.fn.

### 13.2. Không dùng cả hai starter một cách vô tình

Nếu project thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thông thường **ưu tiên Servlet MVC** khi auto-detect web application type. Khi đó Spring WebFlux.fn router có thể không chạy như dự định. Hãy xác định rõ ứng dụng thuộc MVC hay WebFlux qua dependency graph và startup logs.

Có thể có ứng dụng dùng WebClient trong MVC mà không chạy WebFlux server. `WebClient` là HTTP client reactive, không quyết định HTTP server stack.

## 14. Testing trong dự án có hai mô hình routing

Nên chia test thành ba tầng:

| Tầng | Mục tiêu | Công cụ |
|---|---|---|
| Unit service | Kiểm tra business logic độc lập HTTP | JUnit, Mockito khi cần |
| Web slice / route-level | Kiểm tra binding, URL, status, request/response ở tầng web | MockMvc đối với MVC; WebTestClient đối với WebFlux |
| Full integration | Khẳng định cả hai nhóm endpoint thực sự cùng chạy trên một server/app | `@SpringBootTest(RANDOM_PORT)` + HTTP client |

Với Spring MVC, `MockMvc` có thể test controller và route functions được load trong test context. Cần chú ý `@WebMvcTest` là slice test và không phải mọi `RouterFunction`/service beans đều được nạp; có thể cần `@Import` hoặc `@MockBean`/cơ chế mock tương ứng với version. Test HTTP thật ít nhầm hơn khi bạn muốn xác nhận **đồng thời cả hai kiểu endpoint**.

Với WebFlux, `WebTestClient` giúp kiểm tra các endpoint reactive mà không cần tạo client HTTP thủ công. Khi cần chứng minh server thực sự khởi động, hãy dùng `@SpringBootTest(RANDOM_PORT)` và WebTestClient bound to server hoặc một HTTP client thật.

Kiểm thử route collision nên có:

1. Endpoint literal và parameter route có chồng lấp hay không.
2. Functional wildcard có bắt mất annotation route hay static resource không.
3. Đường dẫn cùng URL nhưng khác HTTP method/Accept/Content-Type có chọn đúng nhánh không.
4. Các endpoints cần auth có thể bypass qua route khác không.
5. Error contract có nhất quán khi validation hoặc service thất bại.
6. Context path, servlet path, gateway rewrite và CORS có làm sai URL không.

## 15. Debug khi một nhánh handler không được chọn

### 15.1. Controller hoạt động, functional router bị 404

Các nguyên nhân thường gặp:

- Import nhầm `org.springframework.web.reactive.function.server.RouterFunction` trong project MVC.
- Quên khai báo `@Bean RouterFunction<ServerResponse>`.
- Config class nằm ngoài package component scan.
- Router predicate quá chặt, chẳng hạn chỉ match method GET hoặc header/Accept cụ thể.
- Router có prefix khác URL mà client gửi.
- Custom `HandlerMapping`/order hoặc fallback chặn đường đi.

Cách sửa: kiểm tra package, bean registration, method/path thật, startup log, sau đó tạo test `@SpringBootTest(RANDOM_PORT)`.

### 15.2. Functional route hoạt động nhưng Controller không được gọi

Một nguyên nhân là functional router có cùng path/method hoặc wildcard rộng hơn và chạy trước `RequestMappingHandlerMapping`. Kiểm tra route collision, router order và request predicate; ưu tiên sửa route contract thay vì cố điều chỉnh order để giữ hai handler trùng URL.

Ngoài ra, controller có thể không được component scan, hoặc annotation mapping thực tế là `@RequestMapping` class + `@GetMapping` method tạo URL khác dự kiến.

### 15.3. Ứng dụng khởi động rồi báo ambiguous mapping

Điều này thường xảy ra với **hai annotated methods** đăng ký mapping trùng nhau trong cùng cơ chế annotation mapping. Không nhất thiết là lỗi do một annotated và một functional route trùng URL, vì chúng thuộc hai `HandlerMapping`.

Sửa route cho rõ quyền sở hữu, kiểm tra các property context path/version và không dùng thứ tự khai báo để chọn handler controller.

### 15.4. GET chạy nhưng POST trả 404 hoặc 405

Router `GET(...)` không tự đăng ký POST. Annotation `@GetMapping` cũng không phải `@PostMapping`. Kết quả 404/405 có thể khác do cơ chế xác định allowed methods và các HandlerMapping có mặt.

Khi debug, ghi rõ **HTTP method, path, query, Content-Type, Accept** và response status; đừng chỉ nêu “URL bị lỗi”.

### 15.5. JSON cùng DTO nhưng trả khác content type

Controller có `@RestController` và converter trả object, còn functional handler phải tạo `ServerResponse` với body và optional content type phù hợp. Kiểm tra message converters/serialization config, request `Accept`, response `Content-Type` và DTO.

Nếu có lỗi khi serialize object, stack trace ở tầng adapter/response writer có thể khác nhau. Không giả định mọi lỗi là do handler mapping.

### 15.6. Spring Security hoặc Actuator không khớp kỳ vọng

- Security policies phải bảo vệ cả hai nhánh (annotation và functional).
- Nếu có Spring Boot Actuator và expose an toàn, `/actuator/mappings` có thể giúp xem các mapping đăng ký. Endpoint này **không tồn tại** trong project mẫu vì POM không thêm Actuator.
- Có thể bật log MVC ở môi trường phát triển để xem request mapping, nhưng không nên bật TRACE rộng cho production vì có nguy cơ log nhiều và lộ request metadata.

Một số logger hữu ích trong Spring MVC:

~~~properties
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.servlet.function.support.RouterFunctionMapping=TRACE
~~~

Tùy version, logger names và chi tiết output có thể thay đổi; xác nhận log thực tế thay vì phụ thuộc một chuỗi cố định.

## 16. Migration từng phần mà không làm gián đoạn API

Giả sử project hiện có một controller dành cho reports. Bạn muốn chuyển sang router chức năng để gom predicate phức tạp:

1. **Giữ nguyên service, DTO và error contract.** Chỉ thay lớp HTTP adapter.
2. Tạo router/functional handler cho một URL **khác** trong giai đoạn thử nghiệm, ví dụ `/internal/reports-v2`.
3. Thêm test so kết quả controller và functional handler cho request tương đương: status, headers, JSON body, lỗi và quyền.
4. Kiểm thử sự tương thích của validation/argument binding/exception handling: annotation và functional request APIs không giống nhau.
5. Khi đã xác nhận hoạt động, định tuyến traffic qua gateway hoặc đổi cấu hình route có kiểm soát; **gỡ hoặc vô hiệu hóa route cũ**, tránh giữ hai handler cùng path/method và mong priority tự giải quyết.
6. Theo dõi metrics, latency và error rate; có khả năng rollback.
7. Cuối cùng dọn import/bean không còn dùng, giữ convention route rõ ràng.

Nếu chỉ muốn **bổ sung** chứ không chuyển đổi, không cần thay các controller hiện có: chỉ đăng ký thêm RouterFunction bean với path riêng và tạo test xác minh hoạt động song song.

## 17. Checklist triển khai

- [ ] Đã xác định ứng dụng là **Spring MVC** hay **WebFlux**, không trộn hai package RouterFunction.
- [ ] Với MVC, project có `spring-boot-starter-web`, không cần `@EnableWebMvc` để bật WebMvc.fn.
- [ ] Controller annotation nằm trong component scan và dùng đúng path/method conditions.
- [ ] Router chức năng được trả từ `@Bean RouterFunction<ServerResponse>`, có package import theo stack.
- [ ] Functional routes trong cùng builder đặt **route cụ thể trước route tổng quát**.
- [ ] Có path ownership rõ ràng; không để annotation và functional route giành cùng URL.
- [ ] Service/DTO/domain rules được chia sẻ, logic HTTP adapter không bị nhân đôi.
- [ ] JSON content type, validation và error contract được kiểm thử cho cả hai nhánh.
- [ ] Spring Security bảo vệ cả hai nhóm endpoint, CORS/OPTIONS được kiểm thử.
- [ ] Context path/servlet path/gateway rewrite không làm đường dẫn bị nhân đôi.
- [ ] Có ít nhất một integration test `RANDOM_PORT` truy cập cả annotated và functional endpoints.
- [ ] Khi migration route, đã có test so hành vi và không còn route collision.
- [ ] Với WebFlux, functional handler trả `Mono<ServerResponse>` và annotation controller sử dụng reactive types khi thích hợp.

## Tài liệu chính thức

- [Spring Framework 6.2 — Functional Endpoints (WebMvc.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): WebMvc.fn hoạt động trên cùng DispatcherServlet với annotation controllers, RouterFunction/HandlerFunction, thứ tự router và bean registration.
- [Spring Framework 6.2 — Spring MVC DispatcherServlet](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html): dispatch flow, HandlerMapping và HandlerAdapter.
- [Spring Framework 6.2 — Annotated Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html): request mapping conditions và độ cụ thể.
- [Spring Framework 6.2 — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): reactive RouterFunction/HandlerFunction và khả năng phối hợp cùng annotated controllers.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): MVC autoconfiguration và server.
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): WebFlux autoconfiguration, reactive stack và functional routes.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, random port, web slices.

**Kết luận:** Có thể dùng `@RestController` và `RouterFunction` song song trong **một Spring Boot application**, cùng port, cùng Spring context và cùng business services. Với MVC phải dùng **WebMvc.fn** và `DispatcherServlet`; với WebFlux phải dùng **WebFlux.fn** và `DispatcherHandler`. Điều kiện quan trọng để hệ thống dễ bảo trì là không xung đột routes, giữ security/validation nhất quán và có test HTTP thực chứng minh cả hai nhánh được chọn đúng.

# Controller dùng annotation và handler dùng RouterFunction trong Spring WebFlux

Spring WebFlux có **hai phong cách khai báo HTTP endpoint** trên cùng nền tảng reactive:

1. **Annotated controller:** dùng các annotation quen thuộc như @RestController, @RequestMapping, @GetMapping, @PostMapping, @PathVariable và @RequestBody. Phương thức controller có thể trả về Mono, Flux hoặc những kiểu kết quả được framework hỗ trợ.
2. **Functional endpoint (WebFlux.fn):** dùng RouterFunction để xác định request nào khớp route, rồi chuyển request đến HandlerFunction. Handler làm việc với ServerRequest và trả Mono<ServerResponse>.

Đây là **hai cách mô tả routing và xử lý request**, không phải hai server khác nhau. Trong một Spring Boot WebFlux application, controller annotation và RouterFunction có thể cùng tồn tại. Cả hai đi qua hạ tầng reactive của WebFlux, dùng codec, web filters và các phần tích hợp framework theo cấu hình ứng dụng.

Điểm cần phân biệt ngay từ đầu: **WebFlux.fn** ở package org.springframework.web.reactive.function.server khác **WebMvc.fn** ở package org.springframework.web.servlet.function. Chúng có tên lớp gần giống nhau nhưng hợp đồng xử lý khác nhau: trong WebFlux.fn, handler trả Mono<ServerResponse>, còn trong WebMvc.fn, handler Servlet thường trả ServerResponse trực tiếp.

Bài học triển khai trên Java 17+, Spring Boot 3.5.x / Spring Framework 6.2.x. Ví dụ minh họa một service nghiệp vụ dùng chung, được công bố qua hai họ URL: /annotated/tasks/** và /functional/tasks/**. Điều này giúp quan sát đúng khác biệt mà không phải đổi business logic.

## 1. Bối cảnh: WebFlux xử lý request như thế nào?

Một Spring Boot application có spring-boot-starter-webflux và không có spring-boot-starter-web thường khởi động một reactive web server, mặc định thường là Reactor Netty. Request đi vào được đưa qua WebFilter chain và DispatcherHandler của WebFlux; sau đó framework chọn handler và kết xuất response bằng các result handler / HTTP message codecs phù hợp.

Sơ đồ khái quát:

~~~text
HTTP client
    |
    v
Reactive HTTP server (ví dụ Reactor Netty)
    |
    v
WebFilter chain
    |
    v
DispatcherHandler
    |
    +--- RequestMappingHandlerMapping
    |            |
    |            v
    |      @RestController method
    |
    +--- RouterFunctionMapping
                 |
                 v
           HandlerFunction
                 |
                 v
       Mono<ServerResponse>
    |
    v
HTTP response encoding / writing
~~~

Các thành phần đáng nhớ:

- **DispatcherHandler** là bộ điều phối request của Spring WebFlux, khác DispatcherServlet của Spring MVC.
- **RequestMappingHandlerMapping** tìm endpoint khai báo bằng annotation.
- **RouterFunctionMapping** phát hiện các bean RouterFunction và tìm route phù hợp.
- **HandlerFunctionAdapter** gọi HandlerFunction của functional endpoint.
- **ServerResponseResultHandler** ghi ServerResponse của WebFlux.fn.
- **HttpMessageReader/HttpMessageWriter** hỗ trợ giải mã và mã hóa body; hai phong cách đều dùng hạ tầng WebFlux chứ không buộc bạn tự phân tích JSON.

Mô hình reactive cho phép mô tả kết quả bất đồng bộ bằng publisher, nhưng **không đảm bảo không chặn luồng nếu code bên trong tự dùng JDBC đồng bộ, Thread.sleep, blocking HTTP client hoặc file I/O blocking**. Chọn phong cách routing không quyết định một mình hiệu năng hay tính non-blocking.

## 2. Annotated controller: tư duy gần với Spring MVC

Một controller WebFlux vẫn có thể trông rất quen thuộc:

~~~java
@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<Task> get(@PathVariable long id) {
        return service.findById(id);
    }

    @GetMapping
    public Flux<Task> list() {
        return service.findAll();
    }
}
~~~

Đây là đoạn minh họa chưa đầy đủ import và class liên quan. Nó cho thấy:

- @RestController tương đương @Controller kết hợp @ResponseBody, nên kết quả được ghi vào HTTP response.
- @RequestMapping đặt prefix chung.
- @GetMapping, @PostMapping và các annotation khác khai báo method/path/produces/consumes.
- @PathVariable, @RequestParam, @RequestHeader, @RequestBody ... cho phép framework bind tham số.
- Mono<T> diễn tả tối đa một giá trị hoặc lỗi/hoàn tất rỗng.
- Flux<T> diễn tả một luồng nhiều giá trị.

WebFlux hỗ trợ nhiều kiểu phương thức và reactive return types. Đặc biệt, @RequestBody cũng có thể khai báo Mono<Dto> để quá trình nhận và giải mã body gắn với reactive pipeline.

**Lưu ý 404:** nếu controller chỉ trả Mono.empty() từ một phương thức GET và không đặt trạng thái rõ ràng, không nên mặc định hiểu rằng Spring WebFlux luôn biến kết quả rỗng thành HTTP 404. Trong API thực tế, nên map trường hợp không tìm thấy thành ResponseEntity.notFound() hoặc lỗi nghiệp vụ phù hợp.

## 3. Functional endpoint: RouterFunction và HandlerFunction

WebFlux.fn tách việc mô tả đường đi HTTP khỏi logic xử lý:

~~~java
@Bean
RouterFunction<ServerResponse> taskRoutes(TaskHandler handler) {
    return RouterFunctions.route()
            .GET("/api/tasks", handler::list)
            .GET("/api/tasks/{id}", handler::getById)
            .POST("/api/tasks", handler::create)
            .build();
}
~~~

Một handler function nhận ServerRequest, trả Mono<ServerResponse>:

~~~java
public Mono<ServerResponse> getById(ServerRequest request) {
    long id = Long.parseLong(request.pathVariable("id"));

    return service.findById(id)
            .flatMap(task -> ServerResponse.ok().bodyValue(task))
            .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

Hai đoạn trên minh họa cấu trúc, không dùng trực tiếp trong dự án đầy đủ ở phần sau vì tên URL ví dụ được thay để hai phong cách không trùng nhau.

Các vai trò:

- **RequestPredicate** mô tả điều kiện match HTTP method, path, Accept, Content-Type, query... Có thể kết hợp bằng and, or, negate.
- **RouterFunction<ServerResponse>** lấy request và chọn handler thích hợp. Builder của RouterFunctions.route() giúp tổ chức route rõ ràng.
- **HandlerFunction<ServerResponse>** tương ứng một hàm xử lý ServerRequest và trả publisher của ServerResponse.
- **ServerRequest** bộc lộ path variable, header, query, cookie, request body. Ví dụ request.bodyToMono(NewTask.class).
- **ServerResponse** bộc lộ builder cho status, header, content type và body: ok(), created(...), badRequest(), notFound(), bodyValue(...), body(...).

Khác với annotated controller, functional endpoint **không tự nhận @PathVariable hoặc @RequestBody như tham số Java**. Handler tự lấy dữ liệu từ ServerRequest bằng API tương ứng.

## 4. So sánh trực tiếp hai phong cách

| Tiêu chí | Annotation controller | RouterFunction + HandlerFunction |
|---|---|---|
| Routing | @RequestMapping / @GetMapping / @PostMapping | RouterFunctions.route(), RequestPredicate |
| Lấy path variable | @PathVariable long id | request.pathVariable("id"), tự parse nếu cần |
| Lấy request body | @RequestBody Dto hoặc Mono<Dto> | request.bodyToMono(Dto.class) |
| Viết response | Trả Dto, Mono/Flux, ResponseEntity hoặc Publisher phù hợp | Trả Mono<ServerResponse> |
| HTTP status | @ResponseStatus, ResponseEntity, exception handlers | ServerResponse.ok(), created(), notFound()... |
| Validation | @Valid/@Validated cùng cơ chế binding/validation | Chủ động validate trong handler/service hoặc qua Validator |
| Xử lý lỗi theo endpoint | Reactive operators; @ExceptionHandler / @RestControllerAdvice | Reactive operators, route filter, WebExceptionHandler hoặc error handler dùng chung |
| Cross-cutting cục bộ | Controller advice, annotation, filter/interceptor phù hợp | RouterFunction filter/before/after; WebFilter toàn cục |
| Bố trí mã | HTTP mapping sát phương thức controller | Route definition tách khỏi handler class |
| Phù hợp | Ứng dụng nhiều controller, binding/validation bằng annotation, team quen Spring MVC | Route composition, predicate linh hoạt, handler nhỏ, DSL routing |
| Nền tảng xử lý | Spring WebFlux reactive | Spring WebFlux reactive |

Không nên kết luận kiểu nào luôn nhanh hơn. Với cùng reactive service và HTTP server, chi phí của I/O, database, serialization và nghiệp vụ thường quan trọng hơn khác biệt cú pháp routing. Lựa chọn nên ưu tiên mức rõ ràng của code, quy ước nhóm và yêu cầu HTTP mapping.

## 5. Thiết lập dự án chạy được

Ví dụ dùng **Spring Boot 3.5.0** (Java 17 trở lên) với dependency WebFlux, không thêm spring-boot-starter-web. Điều này giúp tập trung đúng vào WebFlux server, tránh Boot ưu tiên Spring MVC khi cả hai starter đều hiện diện.

Cấu trúc thư mục:

~~~text
webflux-routing-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/routing/
    │   │   ├── RoutingApplication.java
    │   │   ├── Task.java
    │   │   ├── NewTask.java
    │   │   ├── TaskService.java
    │   │   ├── AnnotatedTaskController.java
    │   │   ├── FunctionalTaskHandler.java
    │   │   └── FunctionalTaskRoutes.java
    │   └── resources/application.yml
    └── test/java/com/example/routing/
        └── TaskRoutingTest.java
~~~

### 5.1. Maven pom.xml

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
    <artifactId>webflux-routing-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>webflux-routing-demo</name>

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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

Các phần phụ thuộc được quản lý version bởi Spring Boot parent, không cần chỉ định version riêng.

### 5.2. application.yml

~~~yaml
server:
  port: 8080

spring:
  application:
    name: webflux-routing-demo
~~~

Cổng có thể đổi bằng profile hoặc tham số chạy. Không cần @EnableWebFlux khi Spring Boot đã có auto-configuration.

### 5.3. RoutingApplication.java

~~~java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingApplication {

    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
~~~

Các lớp còn lại nằm dưới cùng package com.example.routing để component scanning tìm thấy.

## 6. Mô hình dữ liệu và service dùng chung

**Task.java**

~~~java
package com.example.routing;

public record Task(long id, String title) {
}
~~~

**NewTask.java**

~~~java
package com.example.routing;

public record NewTask(String title) {
}
~~~

**TaskService.java**

~~~java
package com.example.routing;

import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class TaskService {

    private final ConcurrentMap<Long, Task> tasks =
            new ConcurrentHashMap<>();
    private final AtomicLong ids = new AtomicLong(1);

    public TaskService() {
        tasks.put(1L, new Task(1L, "learn-webflux"));
    }

    public Flux<Task> findAll() {
        return Flux.defer(() ->
                Flux.fromIterable(List.copyOf(tasks.values())));
    }

    public Mono<Task> findById(long id) {
        return Mono.defer(() ->
                Mono.justOrEmpty(tasks.get(id)));
    }

    public Mono<Task> create(NewTask input) {
        return Mono.defer(() -> {
            if (input == null || input.title() == null
                    || input.title().isBlank()) {
                return Mono.error(
                        new IllegalArgumentException("title is required"));
            }

            long id = ids.incrementAndGet();
            Task created = new Task(id, input.title().trim());
            tasks.put(id, created);
            return Mono.just(created);
        });
    }
}
~~~

Đây là **in-memory demo**, không phải repository reactive cho production. ConcurrentHashMap giúp dữ liệu an toàn cơ bản khi nhiều request truy cập đồng thời; AtomicLong cấp ID không trùng trong một process. Khi restart ứng dụng, dữ liệu không được bảo toàn.

Mono.defer và Flux.defer làm thao tác được thực hiện khi subscribe, minh họa tính lazy. Nhưng chính việc đọc/ghi ConcurrentHashMap là thao tác đồng bộ trong bộ nhớ, không tự biến thành non-blocking I/O. Với database thực, dùng driver hoặc repository reactive thích hợp, hoặc cô lập blocking call có chủ đích và kiểm soát thread pool.

Hai giao diện HTTP phía sau đều inject cùng TaskService bean. Vì vậy, một task được tạo ở functional endpoint có thể được đọc ở annotated endpoint và ngược lại.

## 7. AnnotatedTaskController.java: định nghĩa endpoint bằng annotation

~~~java
package com.example.routing;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/annotated/tasks")
public class AnnotatedTaskController {

    private final TaskService service;

    public AnnotatedTaskController(TaskService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<Task> list() {
        return service.findAll();
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Task>> findById(
            @PathVariable long id) {

        return service.findById(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(
                        ResponseEntity.notFound().<Task>build());
    }

    @PostMapping
    public Mono<ResponseEntity<Task>> create(
            @RequestBody Mono<NewTask> body) {

        return body.flatMap(service::create)
                .map(task -> ResponseEntity
                        .created(URI.create(
                                "/annotated/tasks/" + task.id()))
                        .body(task))
                .onErrorResume(
                        IllegalArgumentException.class,
                        error -> Mono.just(
                                ResponseEntity.badRequest()
                                        .<Task>build()));
    }
}
~~~

**Giải thích theo request:**

- GET /annotated/tasks trả Flux<Task>. Codec của WebFlux ghi các phần tử ra response theo media type được chọn.
- GET /annotated/tasks/1 lấy id theo @PathVariable và trả Mono<ResponseEntity<Task>>. Nếu có Task thì HTTP 200 và JSON; nếu Mono rỗng thì HTTP 404.
- POST /annotated/tasks nhận body dưới dạng Mono<NewTask>, chuyển tới service, trả HTTP 201 Created cùng header Location và JSON của Task vừa tạo.
- Nếu title không hợp lệ, service phát IllegalArgumentException; đoạn onErrorResume trong ví dụ chuyển riêng lỗi này thành HTTP 400.
- Body rỗng hoặc JSON không giải mã được còn được framework xử lý theo quy tắc request-body binding; không nên mặc định coi chúng tương đương IllegalArgumentException của service.

Phương thức Java không gọi subscribe(). Khi xử lý request, Spring WebFlux subscribe publisher và quản lý vòng đời xử lý/ghi response.

**Lưu ý:** HttpStatus được import ở ví dụ nhưng không cần trong class này; có thể bỏ import mà không ảnh hưởng biên dịch. Ví dụ Java chấp nhận import không dùng.

## 8. FunctionalTaskHandler.java: xử lý ServerRequest, tạo ServerResponse

~~~java
package com.example.routing;

import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@Component
public class FunctionalTaskHandler {

    private final TaskService service;

    public FunctionalTaskHandler(TaskService service) {
        this.service = service;
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(service.findAll(), Task.class);
    }

    public Mono<ServerResponse> findById(ServerRequest request) {
        final long id;

        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException ex) {
            return ServerResponse.badRequest().build();
        }

        return service.findById(id)
                .flatMap(task -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(task))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(NewTask.class)
                .flatMap(service::create)
                .flatMap(task -> ServerResponse
                        .created(URI.create(
                                "/functional/tasks/" + task.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(task))
                .onErrorResume(
                        IllegalArgumentException.class,
                        error -> ServerResponse.badRequest().build())
                .switchIfEmpty(ServerResponse.badRequest().build());
    }
}
~~~

Các điểm khác biệt quan trọng:

1. Không có @GetMapping trong handler; route được khai báo ở một class riêng.
2. request.pathVariable("id") trả String nên phải parse thành long. Nếu không hợp lệ, handler trả 400.
3. request.bodyToMono(NewTask.class) đọc JSON body theo codec.
4. ServerResponse.ok(), ServerResponse.created(...) và ServerResponse.notFound() trực tiếp thể hiện status.
5. .body(publisher, Task.class) xuất publisher của nhiều Task; .bodyValue(task) ghi một giá trị cụ thể.
6. switchIfEmpty xử lý nhánh không tìm thấy dữ liệu hoặc không có body.
7. onErrorResume được dùng đúng cho lỗi nghiệp vụ minh họa; ứng dụng thật nên thiết kế mã lỗi và message an toàn, nhất quán hơn.

**Không gọi block()** bên trong handler. Handler trả Mono để WebFlux thực hiện bất đồng bộ. Việc dùng ServerResponse không đồng nghĩa response được ghi vào socket ngay tại dòng gọi bodyValue; phương thức tạo một Mono biểu diễn quá trình hoàn tất response.

## 9. FunctionalTaskRoutes.java: RouterFunction bean

~~~java
package com.example.routing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FunctionalTaskRoutes {

    @Bean
    RouterFunction<ServerResponse> taskRoutes(
            FunctionalTaskHandler handler) {

        return RouterFunctions.route()
                .GET("/functional/tasks", handler::list)
                .GET("/functional/tasks/{id}", handler::findById)
                .POST("/functional/tasks", handler::create)
                .build();
    }
}
~~~

Spring Boot phát hiện bean RouterFunction khi tạo hạ tầng WebFlux. Route GET/POST này sẽ gọi các phương thức tương ứng trong FunctionalTaskHandler.

Trong ví dụ, annotated controller dùng /annotated/tasks còn functional router dùng /functional/tasks. Hai họ route tách nhau để dễ kiểm thử, không gây cạnh tranh mapping.

**Thứ tự route trong WebFlux.fn có ý nghĩa.** Nếu cùng một builder có các pattern chồng nhau, route được xét theo thứ tự đăng ký. Nên đặt route cụ thể trước route tổng quát; ví dụ /functional/tasks/search trước /functional/tasks/{id} nếu muốn search là từ khóa cố định. Annotation-based mappings có quy tắc chọn method cụ thể riêng. Đừng giả định tất cả route styles áp dụng cùng cơ chế độ ưu tiên.

## 10. Chạy và thử HTTP từ terminal

Từ thư mục webflux-routing-demo:

~~~bash
mvn test
mvn spring-boot:run
~~~

Giả sử ứng dụng chạy cổng 8080, tạo task qua annotation:

~~~bash
curl -i -X POST "http://localhost:8080/annotated/tasks" \
  -H "Content-Type: application/json" \
  -d '{"title":"annotated-created"}'
~~~

Kết quả mong đợi: HTTP 201, Location chỉ task mới và JSON có id/title. Không cố định id nếu đã có request tạo task trước đó.

Tạo task bằng functional route:

~~~bash
curl -i -X POST "http://localhost:8080/functional/tasks" \
  -H "Content-Type: application/json" \
  -d '{"title":"functional-created"}'
~~~

Đọc task mặc định qua hai cách:

~~~bash
curl -i "http://localhost:8080/annotated/tasks/1"
curl -i "http://localhost:8080/functional/tasks/1"
~~~

Cả hai đều đọc cùng TaskService, nên JSON body chứa:

~~~json
{"id":1,"title":"learn-webflux"}
~~~

Trường hợp không tồn tại:

~~~bash
curl -i "http://localhost:8080/annotated/tasks/99999"
curl -i "http://localhost:8080/functional/tasks/99999"
~~~

Cả hai được thiết kế trả HTTP 404. Response body của lỗi phụ thuộc error handling/codec; không nên dựa vào một đoạn JSON lỗi duy nhất nếu chưa chuẩn hóa hợp đồng API.

Trường hợp title rỗng:

~~~bash
curl -i -X POST "http://localhost:8080/functional/tasks" \
  -H "Content-Type: application/json" \
  -d '{"title":"   "}'
~~~

Handler functional chuyển IllegalArgumentException từ TaskService thành HTTP 400. Tương tự annotated controller xử lý trường hợp này. Tất cả ví dụ chỉ dùng state trong bộ nhớ; ứng dụng restart sẽ mất task do người dùng tạo.

## 11. Khi cần predicate phức tạp hoặc route lồng nhau

RouterFunctions.route() builder hỗ trợ nhiều RequestPredicate:

~~~java
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.web.reactive.function.server.RequestPredicates.accept;

RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/api/tasks", accept(APPLICATION_JSON), handler::list)
        .POST("/api/tasks", handler::create)
        .build();
~~~

Đây là đoạn minh họa tách rời, không thay thế bean routes của dự án đang chạy.

Ở đây GET chỉ match khi Accept header thỏa điều kiện JSON. Nếu client gửi Accept header không phù hợp, route này có thể không khớp; việc không khớp route không phải một exception tự động do handler ném ra.

Có thể lồng route theo path:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .path("/api/tasks", builder -> builder
                .GET("/{id}", handler::findById)
                .GET(handler::list)
                .POST(handler::create))
        .build();
~~~

Nhờ nested routing, prefix /api/tasks chỉ khai báo một lần. Để dùng builder này, các phương thức handler phải chấp nhận ServerRequest và trả Mono<ServerResponse>.

**Các cách kết hợp:** RouterFunction.and(...), RouterFunction.andRoute(...), RouterFunctions.route().add(...), hoặc nhiều bean RouterFunction do Spring Boot gom lại. Khi module lớn, chia router theo bounded context và chú ý thứ tự route thay vì để một class hàng trăm dòng.

## 12. Binding, validation và lỗi: annotation có lợi thế gì?

Annotated controller tận dụng khả năng của Spring Framework để bind và validate tham số ngay tại chữ ký method.

Ví dụ với dependency spring-boot-starter-validation:

~~~java
public record NewTaskRequest(
        @NotBlank String title,
        @Size(max = 120) String description) {
}

@PostMapping
public Mono<Task> create(
        @Valid @RequestBody Mono<NewTaskRequest> body) {
    return body.flatMap(service::createValidated);
}
~~~

Đây là ví dụ riêng để giải thích Bean Validation; phương thức createValidated và kiểu NewTaskRequest chưa được khai báo trong dự án hoàn chỉnh ở trên. Không sao chép đoạn này vào AnnotatedTaskController nếu chưa bổ sung service contract và import jakarta.validation.*.

Trong WebFlux, @Valid kết hợp @RequestBody có thể làm phát sinh WebExchangeBindException. Khi có method-level constraints, HandlerMethodValidationException cũng có thể xuất hiện. Dự án nên xử lý cả hai theo chính sách error response.

Với functional endpoint, handler không tự nhận các annotation validation trên tham số ServerRequest. Có thể:

- Parse body thành DTO với request.bodyToMono(Dto.class).
- Dùng Validator do Spring quản lý để kiểm tra DTO.
- Hoặc đặt validation trong application service, rồi map lỗi thành ServerResponse phù hợp.
- Chuẩn hóa error response để cả hai route styles trả cùng error code/message.

**Không coi việc dùng @Valid là tự động xuất hiện cho functional handler.** Validation phải có lớp thực thi cụ thể.

### 12.1. Hai cách xử lý lỗi

Annotated controller có thể dùng @ExceptionHandler trong controller hoặc @RestControllerAdvice để gom xử lý exception. Đây là mô hình quen thuộc khi muốn đưa lỗi nghiệp vụ thành HTTP response nhất quán.

Functional handler thường dùng onErrorResume, xử lý status trực tiếp qua ServerResponse, hoặc một WebExceptionHandler / cơ chế error handling dùng chung cho nhiều route. Route filter cũng có thể bao quanh handler nếu chỉ cần chính sách cục bộ.

Nếu cần cả hai style cùng trả RFC 9457 Problem Details, hãy thiết kế một error contract chung và kiểm thử từng endpoint. Đừng giả định rằng @ControllerAdvice luôn áp dụng y hệt cho lỗi của functional handler: cơ chế gọi handler khác nhau.

## 13. Filters: WebFilter và HandlerFilterFunction

Mục đích "chạy trước/sau request" có hai tầng cần phân biệt:

- **WebFilter:** nằm trong filter chain của Spring WebFlux; có thể tác động tới cả annotated controllers và functional endpoints, tùy phạm vi, thứ tự và cấu hình. Đây là lựa chọn cho xử lý cross-cutting toàn ứng dụng.
- **HandlerFilterFunction:** là filter của WebFlux.fn, được áp dụng cho router/nhóm route chức năng. Nó nhận ServerRequest và HandlerFunction tiếp theo, trả Mono<ServerResponse>. Đây là lựa chọn khi logic gắn chặt một nhóm functional endpoint.

Một filter functional đơn giản:

~~~java
return RouterFunctions.route()
        .GET("/api/health", request ->
                ServerResponse.ok().bodyValue("up"))
        .filter((request, next) -> {
            if ("blocked".equals(
                    request.headers().firstHeader("X-Mode"))) {
                return ServerResponse.status(403).build();
            }
            return next.handle(request);
        })
        .build();
~~~

Đoạn trên minh họa cú pháp bên trong một phương thức trả RouterFunction<ServerResponse>, không phải file Java độc lập. Nó chỉ kiểm tra header giả định, không phải hệ thống authorization thật.

Spring Security WebFlux dùng SecurityWebFilterChain và các thành phần security reactive. Không dùng một HandlerFilterFunction giản đơn để thay hoàn toàn authentication, authorization, CSRF, CORS và security context propagation.

**Lưu ý luồng:** không gọi subscribe() trong filter rồi trả một response khác. Hãy trả về chính publisher tạo từ next.handle(request), có thể thêm toán tử như doOnNext/doOnError để quan sát mà không phá pipeline.

## 14. JSON, HTTP status và content negotiation

Ở annotated controller:

~~~java
@GetMapping(path = "/items", produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<ItemDto> items() {
    return service.findAllItems();
}
~~~

Framework dựa vào annotation, return type và codec để tạo response. Có thể dùng ResponseEntity hoặc @ResponseStatus để kiểm soát status/headers.

Ở functional handler:

~~~java
public Mono<ServerResponse> items(ServerRequest request) {
    return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(service.findAllItems(), ItemDto.class);
}
~~~

Status, content type và body được cấu hình qua ServerResponse builder. Hai đoạn này chỉ minh họa API; ItemDto/findAllItems chưa có trong demo hoàn chỉnh.

Với streaming, cần hiểu sự khác biệt giữa publisher **phát nhiều phần tử** và wire protocol **đưa từng phần tử tới client**. Flux<T> với application/json có thể được serialize thành JSON array; không nên giả định mỗi onNext đồng nghĩa một frame phản hồi mà client nhận ngay.

Khi cần **Server-Sent Events**, dùng media type text/event-stream cùng Flux phù hợp. Với functional endpoint, có thể ghi publisher dưới dạng SSE; với annotated controller, có thể dùng @GetMapping(produces = MediaType.TEXT_EVENT_STREAM_VALUE).

### 14.1. Khi nào cần ResponseEntity hoặc ServerResponse?

- Annotated controller trả DTO/Mono<DTO> rất gọn với HTTP 200 mặc định.
- Khi cần 201 Created, Location, ETag hoặc 404 rõ ràng, ResponseEntity<T> và Mono<ResponseEntity<T>> là lựa chọn phù hợp.
- Functional endpoint luôn trả Mono<ServerResponse>; cần thiết lập status và body bằng builder.
- Không nhầm Mono<ResponseEntity<Flux<T>>> với Mono<ResponseEntity<T>>: vị trí publisher trong return type ảnh hưởng thời điểm body được viết.

## 15. Reactive semantics: không block, không subscribe tay

Đây là phần quan trọng hơn cú pháp route.

**Mono** đại diện tối đa một signal giá trị; **Flux** đại diện nhiều signal. Publisher thường lazy: thao tác cần subscription để bắt đầu.

Sai lầm thường gặp trong handler WebFlux:

~~~java
Task task = webClient.get()
        .uri("/tasks/1")
        .retrieve()
        .bodyToMono(Task.class)
        .block();  // Không nên trong luồng xử lý reactive.
~~~

Hành vi chờ ở block() có thể làm nghẽn event-loop thread hoặc bị Reactor phát hiện là blocking không cho phép. Cách đúng là trả publisher:

~~~java
return webClient.get()
        .uri("/tasks/1")
        .retrieve()
        .bodyToMono(Task.class)
        .flatMap(task -> ServerResponse.ok().bodyValue(task));
~~~

Nếu phía annotation:

~~~java
@GetMapping("/remote")
public Mono<Task> remote() {
    return webClient.get()
            .uri("/tasks/1")
            .retrieve()
            .bodyToMono(Task.class);
}
~~~

Các ví dụ này chỉ minh họa ghép WebClient vào controller/handler, giả định webClient bean và DTO đã có. Không copy cả ba đoạn vào demo đầy đủ nếu chưa định nghĩa WebClient bean.

**Tránh tự gọi subscribe():**

~~~java
Mono<Task> result = service.findById(1);
result.subscribe(task -> log.info("{}", task));
return Mono.empty();
~~~

Đoạn này cố ý minh họa anti-pattern. Nếu gọi subscribe() bên trong handler rồi trả Mono khác, framework không quản lý được completion, error và cancellation của công việc đã tách ra.

**Nếu hệ thống bắt buộc gọi thư viện blocking**, không được giả vờ rằng Mono.just(blockingCall()) là non-blocking. Có thể cân nhắc Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()) như biện pháp cách ly tạm thời, nhưng phải kiểm soát số lượng thread/concurrency, timeout và tải. Về dài hạn, chọn reactive driver phù hợp khi thực sự muốn non-blocking end-to-end.

## 16. Backpressure và cancellation

Cả annotated controller lẫn functional handler đều dựa trên Reactive Streams. Tầng ứng dụng có thể mô tả dữ liệu bằng Flux, hỗ trợ điều tiết nhu cầu tiêu thụ, propagation lỗi và cancellation theo khả năng của từng publisher và transport.

Ví dụ service có luồng sự kiện:

~~~java
Flux<String> events = Flux.interval(Duration.ofSeconds(1))
        .map(index -> "tick-" + index);
~~~

Đây là ví dụ độc lập về Reactor và cần import java.time.Duration, reactor.core.publisher.Flux. Flux.interval dùng scheduler để phát theo nhịp; không dùng cho thông báo nghiệp vụ bền vững nếu chưa có persistence.

Với annotated controller, có thể trả Flux<ServerSentEvent<String>>; với functional endpoint, có thể thiết lập contentType(MediaType.TEXT_EVENT_STREAM) rồi body(events, String.class). Khi client ngắt kết nối, cancellation có thể truyền ngược lên pipeline để giải phóng tài nguyên theo thiết kế.

**Không đồng nhất backpressure với việc mạng vô hạn dung lượng**. Buffering, giới hạn codec, cơ chế ghi mạng và công việc của nguồn dữ liệu đều ảnh hưởng. Nếu phía nguồn là một API không hỗ trợ backpressure, ứng dụng có thể vẫn cần bộ đệm, chính sách drop hoặc kiểm soát tốc độ.

## 17. Kiểm thử cả hai phong cách bằng WebTestClient

WebTestClient dùng được cho annotation controllers, functional routers và HTTP server thực tế. Với Spring Boot có thể dùng integration test trên random port để kiểm tra hai route styles cùng hoạt động trong một ApplicationContext.

**src/test/java/com/example/routing/TaskRoutingTest.java**

~~~java
package com.example.routing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TaskRoutingTest {

    @Autowired
    WebTestClient client;

    @Test
    void bothStylesCanReadTheSameTask() {
        client.get()
                .uri("/annotated/tasks/1")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("learn-webflux");

        client.get()
                .uri("/functional/tasks/1")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("learn-webflux");
    }

    @Test
    void functionalCreationIsVisibleThroughAnnotatedRoute() {
        Task created = client.post()
                .uri("/functional/tasks")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NewTask("reactive-routing"))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(Task.class)
                .returnResult()
                .getResponseBody();

        assertThat(created).isNotNull();

        client.get()
                .uri("/annotated/tasks/{id}", created.id())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("reactive-routing");
    }

    @Test
    void bothStylesReturnNotFound() {
        client.get()
                .uri("/annotated/tasks/99999")
                .exchange()
                .expectStatus().isNotFound();

        client.get()
                .uri("/functional/tasks/99999")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void functionalHandlerRejectsBlankTitle() {
        client.post()
                .uri("/functional/tasks")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NewTask("  "))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

Với RANDOM_PORT, Spring Boot tạo server trên một cổng ngẫu nhiên và cấu hình WebTestClient phù hợp cho kiểm thử HTTP. Các test không cần tự hard-code 8080.

Bộ test kiểm tra các hành vi quan trọng: hai route cùng đọc dữ liệu, POST functional tạo dữ liệu để annotated route đọc, 404 được giữ rõ ràng, body không hợp lệ bị từ chối. Đây là các tiêu chí cụ thể hơn việc chỉ kiểm tra bean RouterFunction tồn tại.

Chạy:

~~~bash
mvn test
~~~

Khi test thành công, Maven trả exit code 0. Không đưa số lượng log line, cổng ngẫu nhiên hoặc thứ tự Task trong list vào assertion vì các giá trị đó không ổn định giữa lần chạy.

### 17.1. Test không cần mở server thật

Spring Framework hỗ trợ:

~~~java
WebTestClient.bindToController(new MyController(...)).build();
WebTestClient.bindToRouterFunction(routerFunction).build();
~~~

Đây là ví dụ về API test, không phải class có thể sao chép nguyên xi khi chưa tạo đối tượng controller/router tương ứng. BindToController phù hợp khi muốn cô lập một annotated controller; bindToRouterFunction phù hợp để kiểm thử route + functional handler. Test tích hợp toàn ứng dụng dùng ApplicationContext hay RANDOM_PORT có khả năng phát hiện lỗi auto-configuration/bean routing mà unit test đơn lẻ có thể bỏ qua.

Với @WebFluxTest, cần hiểu đây là test slice cho WebFlux, không đồng nghĩa tự động nạp mọi repository/service/RouterFunction tùy chỉnh. Hãy import đúng configuration cần test hoặc dùng SpringBootTest khi mục tiêu là đối chiếu cả hai phong cách trong ứng dụng thực.

## 18. CORS, bảo mật và observability

Hai phong cách không tách khỏi trách nhiệm bảo mật ứng dụng.

**Spring Security WebFlux:** cấu hình SecurityWebFilterChain bảo vệ HTTP request ở tầng reactive. Nó có thể áp dụng bất kể handler cuối cùng được chọn bằng annotation hay functional route. Đừng coi việc router không có annotation @PreAuthorize là mặc định không cần authorization.

**CORS:** annotated controllers có thể dùng @CrossOrigin hoặc cấu hình WebFlux CORS. Với functional routes, có thể dùng WebFlux CORS configuration hoặc filter phù hợp. Tránh khai báo CORS lệch nhau khiến một họ route nhận request từ frontend còn họ kia bị browser chặn.

**Logging/tracing:** có thể sử dụng WebFilter hoặc cơ chế observation/tracing của Spring Boot; giữ correlation ID trong reactive context đúng cách, thay vì giả định ThreadLocal hiện tại được giữ qua mọi scheduler switch.

**Rate limit / audit:** các nhu cầu áp dụng toàn bộ request nên ở lớp WebFilter, API gateway hoặc service security phù hợp. HandlerFilterFunction hữu ích cho nhóm router, không thay thế security layer chung.

**Timeout:** nếu controller hoặc handler gọi WebClient, cần đặt timeout của outbound HTTP client và ngân sách thời gian request phù hợp. Chỉ dùng Reactor timeout không đảm bảo mọi socket timeout trong mọi client connector đã được cấu hình.

## 19. Lựa chọn annotation hay RouterFunction theo dự án

**Ưu tiên annotated controller khi:**

- Team đã quen @RestController và các annotation Spring MVC.
- Có nhiều phương thức với validation, argument binding hoặc OpenAPI documentation theo annotation.
- Mỗi controller gắn một phần nghiệp vụ rõ ràng; mapping không quá phức tạp.
- Muốn tái sử dụng cách tổ chức controller-service-repository.

**Ưu tiên RouterFunction khi:**

- Muốn thể hiện các route như một bảng khai báo tập trung hoặc DSL rõ ràng.
- Route cần nhiều điều kiện kết hợp như path, Accept, Content-Type.
- Muốn compose/router nesting theo module và áp dụng filter cục bộ.
- Muốn handler dễ diễn giải như hàm nhận ServerRequest, trả Mono<ServerResponse>.

**Cho phép dùng cùng lúc khi:**

- Ứng dụng di chuyển dần từ annotated sang functional (hoặc ngược lại).
- Có bounded contexts khác nhau được sở hữu bởi các team khác nhau.
- Đã có quy tắc tránh trùng URL và thống nhất error contract, security, response format.

Không nên dùng cả hai chỉ để nhân đôi toàn bộ endpoint khi không có nhu cầu thật. Trong ví dụ, hai API công bố cùng một TaskService chỉ nhằm học tập và kiểm thử.

## 20. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân hay gặp | Cách xử lý |
|---|---|---|
| RouterFunction bean có mặt nhưng request 404 | Sai path, HTTP method, predicate hoặc cấu hình reactive | Kiểm tra method/path/header, RouterFunctionMapping và WebFlux starter |
| Tên lớp RouterFunction đúng nhưng handler có kiểu trả về sai | Import nhầm org.springframework.web.servlet.function.* | Dùng org.springframework.web.reactive.function.server.* và Mono<ServerResponse> |
| GET /tasks/{id} nhận /tasks/search và báo 400 | Route tổng quát đứng trước route cụ thể | Đặt /tasks/search trước /tasks/{id}, hoặc giới hạn predicate |
| Controller trả Mono.empty() nhưng response không phải 404 | Chưa map trạng thái cho trường hợp không tồn tại | Dùng ResponseEntity.notFound hoặc lỗi nghiệp vụ |
| Functional handler báo 500 thay vì 400 khi DTO sai | Chưa validate và map lỗi | Gắn validation/service rule, trả ServerResponse.badRequest phù hợp |
| Thêm cả starter-web và starter-webflux nhưng không thấy WebFlux server | Boot thường ưu tiên Spring MVC | Chỉ dùng WebFlux starter khi chủ ý reactive server; rà soát application type |
| Endpoint có Mono nhưng vẫn nghẽn tải | Code bên trong gọi JDBC, file I/O hoặc block() | Dùng reactive driver hoặc cô lập blocking call, theo dõi scheduler |
| Handler tự subscribe rồi trả Mono.empty | Tách công việc khỏi request lifecycle | Trả publisher gốc, để framework subscribe |
| Router filter không chạy ở controller annotation | HandlerFilterFunction chỉ áp dụng router đã đăng ký filter | Dùng WebFilter nếu cần áp dụng cho tất cả endpoint |
| JSON response khác giữa annotation và functional | Codec/status/content type/error contract cấu hình khác | Đặt chung response contract và test 2 phong cách |
| @ControllerAdvice không xử lý lỗi functional như kỳ vọng | Handler execution path khác | Dùng WebExceptionHandler / error handling chung và mapping tại handler |
| Test chỉ pass khi chạy một mình | Shared in-memory state hoặc hard-code ID/port | Test theo ID lấy từ response; dùng RANDOM_PORT và dữ liệu độc lập |
| Streaming không ra từng bản tin | Media type và buffering không phù hợp | Dùng text/event-stream khi cần SSE, kiểm tra client/proxy buffering |
| Dùng annotation của Spring MVC trong ứng dụng reactive | Import/cấu hình thuộc servlet stack | Kiểm tra package WebFlux và runtime DispatcherHandler |

## 21. Checklist áp dụng trong dự án

1. Xác định server stack thật sự là Spring WebFlux, không chỉ là một MVC app có WebClient.
2. Khi dùng WebFlux.fn, import org.springframework.web.reactive.function.server, không import org.springframework.web.servlet.function.
3. Giữ controller và handler mỏng; nghiệp vụ nằm ở service/repository dùng chung.
4. Với annotation, dùng @RequestBody, @PathVariable, @RequestParam và ResponseEntity khi phù hợp.
5. Với functional route, tách RouterFunction khỏi HandlerFunction; handler đọc ServerRequest và tạo ServerResponse.
6. Định nghĩa rõ HTTP status cho 200/201/400/404 và lỗi upstream.
7. Sắp xếp route functional từ cụ thể đến tổng quát, tránh chồng pattern.
8. Không gọi block() hoặc subscribe() trong luồng xử lý WebFlux.
9. Có validation cho request body và xử lý lỗi thống nhất cho hai kiểu endpoint.
10. Dùng WebFilter/SecurityWebFilterChain cho chính sách xuyên suốt ứng dụng; chỉ dùng route filter khi cần phạm vi router.
11. Kiểm thử WebTestClient cho controller, router và toàn ứng dụng; dùng RANDOM_PORT khi muốn kiểm tra server thật.
12. Theo dõi throughput/latency, giới hạn codec, cancellation, backpressure và hiệu năng I/O khi chạy production.

## 22. Kết luận

**Annotated controller và RouterFunction là hai lối vào HTTP trên cùng reactive stack của Spring WebFlux.** Controller dựa vào annotation để ánh xạ request và bind tham số trực tiếp vào method; WebFlux.fn định nghĩa RouterFunction để chọn HandlerFunction nhận ServerRequest và trả Mono<ServerResponse>.

Không có quy tắc "RouterFunction luôn reactive hơn controller". Cả hai đều có thể dùng Mono/Flux, codec và WebFilter của WebFlux. Hãy chọn theo độ rõ ràng và yêu cầu routing, tránh import nhầm WebMvc.fn, tránh blocking code và thiết kế đồng nhất HTTP status, validation, security và kiểm thử.

## Tài liệu chính thức

- [Spring Framework 6.2 — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html)
- [Spring Framework 6.2 — Annotated Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-controller.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)

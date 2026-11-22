# Xây cùng một hợp đồng bằng controller và endpoint hàm trong Spring WebFlux

**Module:** Spring Framework - reactive  
**Chủ đề cha:** Thực hành tổng hợp  
**Bài học:** Xây cùng một hợp đồng bằng controller và endpoint hàm

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả hai mô hình lập trình HTTP của Spring WebFlux: annotated controller và functional endpoint.
2. Phân biệt `@RestController`/`@RequestMapping` với `RouterFunction`/`HandlerFunction`.
3. Xây dựng cùng một HTTP API contract bằng cả hai phong cách: route, method, path variable, query/body, status, header, JSON response và lỗi.
4. Tách DTO, validation, business service và persistence khỏi lớp HTTP để hai adapter dùng chung logic.
5. Hiểu cách Spring WebFlux giải mã body, serialize Publisher, xử lý `Mono`/`Flux` và backpressure.
6. Áp dụng Bean Validation cho controller và functional handler; giữ response lỗi nhất quán.
7. Chọn cách xử lý 404, 400, 201 Created, Location header và content type.
8. Viết test contract bằng `WebTestClient` qua HTTP server thật, so sánh hai cách triển khai.
9. Hiểu cách mở rộng functional routes bằng nested routes, predicates và `HandlerFilterFunction`.
10. Biết khi nào controller hoặc functional endpoint phù hợp hơn; tránh chọn dựa trên giả định một phong cách luôn nhanh hơn.

## 1. Cùng một API contract, hai cách khai báo

Spring WebFlux hỗ trợ hai cách định nghĩa HTTP endpoint:

- **Annotated controller:** khai báo class/method bằng annotation như `@RestController`, `@GetMapping`, `@PostMapping`, `@PathVariable` và `@RequestBody`.
- **Functional endpoint:** mô tả điều kiện route bằng `RouterFunction<ServerResponse>`, rồi chuyển request cho `HandlerFunction<ServerResponse>` để tạo response.

Cả hai đều nằm trên WebFlux reactive stack, đều có thể trả `Mono<T>` hoặc `Flux<T>`, dùng cùng codec, server runtime, Reactor và WebClient. Functional endpoint không có nghĩa là “không dùng Spring” hoặc “không reactive”; controller cũng không phải Spring MVC nếu ứng dụng đang chạy WebFlux.

### 1.1. Hợp đồng API của bài thực hành

Ta xây dựng một API quản lý task nhỏ với bốn operation:

| Method | Resource path | Thành công | Không tìm thấy / lỗi |
| --- | --- | --- | --- |
| GET | `/tasks` | 200 + danh sách task JSON | — |
| GET | `/tasks/{id}` | 200 + một task | 404 nếu id không tồn tại |
| POST | `/tasks` | 201 + task vừa tạo + Location header | 400 nếu title trống |
| POST | `/tasks/{id}/complete` | 200 + task đã hoàn tất | 404 nếu id không tồn tại |

Request tạo task:

```http
POST /tasks
Content-Type: application/json

{
  "title": "Prepare release"
}
```

Response thành công:

```http
HTTP/1.1 201 Created
Location: /tasks/1
Content-Type: application/json

{
  "id": 1,
  "title": "Prepare release",
  "completed": false
}
```

Response validation error có schema chung:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "title: must not be blank"
}
```

Trong project demo, hai adapter chạy đồng thời nên có prefix:

- Annotated controller: `/controller/tasks`.
- Functional endpoint: `/functional/tasks`.

Phần path phía sau prefix, HTTP method, status, header và JSON contract giống nhau. Prefix chỉ giúp cả hai adapter cùng tồn tại trong một process để test đối chiếu. Nếu triển khai riêng từng phong cách, có thể dùng chung canonical path `/api/tasks`; không đăng ký hai handler trùng method và path trong cùng một router/application nếu không có quy tắc phân giải rõ ràng.

## 2. Kiến trúc: adapter HTTP dùng chung application service

Một API nên tách ba trách nhiệm:

```text
                HTTP Request
                     |
            +--------+--------+
            |                 |
            v                 v
   Annotated Controller   Functional Router
            |                 |
            v                 v
     Controller methods   HandlerFunction
            |                 |
            +--------+--------+
                     |
                     v
                TaskService
                     |
                     v
             Repository / Store
                     |
                     v
              Domain response
```

Controller và functional handler là hai **HTTP adapter**. Chúng chịu trách nhiệm route, bind request, validate input ở biên, chọn status/header và serialize response. Business rule nằm trong service, không nên nhân đôi giữa hai adapter.

Trong ứng dụng thật, service có thể gọi Spring Data R2DBC, repository reactive, WebClient hoặc hệ thống khác. Ví dụ ở bài này dùng in-memory store để tập trung vào sự khác biệt giữa hai kiểu endpoint mà không bị nhiễu bởi database configuration.

### 2.1. Contract trước, implementation sau

Trước khi viết controller hoặc router, chốt các điểm sau:

- Resource và path.
- HTTP method.
- Kiểu request và response.
- Status code cho từng trường hợp.
- Header cần có, đặc biệt Location khi tạo tài nguyên.
- Quy tắc validation và schema lỗi.
- Hành vi khi resource không tồn tại.
- Content type và cách stream dữ liệu.

Khi contract đã rõ, có thể thay adapter mà client không phải thay đổi cách gọi. Đây là lợi ích quan trọng hơn việc so sánh số annotation hay số dòng code.

## 3. Annotated controller trong WebFlux

### 3.1. Cách khai báo

Controller dùng annotation để Spring ánh xạ method HTTP:

```java
@RestController
@RequestMapping("/controller/tasks")
class TaskController {

    @GetMapping
    public Flux<TaskView> list() {
        // ...
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<TaskView>> get(
            @PathVariable long id) {
        // ...
    }

    @PostMapping
    public Mono<ResponseEntity<TaskView>> create(
            @Valid @RequestBody CreateTaskRequest request) {
        // ...
    }
}
```

`@RestController` kết hợp `@Controller` và `@ResponseBody`. Return value được xử lý bởi WebFlux message writers/HTTP codecs. Với reactive return type, framework subscribe và ghi kết quả theo lifecycle HTTP.

### 3.2. Argument resolution

Spring có thể tự bind nhiều phần của HTTP request vào tham số method:

| Annotation / kiểu tham số | Dữ liệu nhận |
| --- | --- |
| `@PathVariable` | Thành phần động trong path. |
| `@RequestParam` | Query parameter hoặc form parameter theo cách bind WebFlux hỗ trợ. |
| `@RequestHeader` | HTTP header. |
| `@CookieValue` | Cookie. |
| `@RequestBody` | Request body qua codec. |
| `@Valid` / `@Validated` | Kích hoạt Bean Validation phù hợp với tham số. |
| `ServerWebExchange` | Truy cập request/response exchange mức thấp hơn. |

Ví dụ:

```java
@GetMapping("/search")
public Flux<TaskView> search(
        @RequestParam(required = false) String title,
        @RequestHeader(name = "X-Request-Id", required = false)
        String requestId) {
    // Dùng title và requestId trong service.
}
```

Đoạn trên minh họa argument binding; method body cần được triển khai theo contract cụ thể. Với body reactive, tham số có thể là `Mono<CreateTaskRequest>` hoặc `Flux<Line>` nếu muốn xử lý stream thay vì materialize một object.

### 3.3. Return type và status

- Trả `Mono<TaskView>`: framework thường tạo response 200 với một object nếu có dữ liệu.
- Trả `Flux<TaskView>`: framework serialize nhiều phần tử theo media type và negotiation.
- Trả `ResponseEntity<T>` hoặc `Mono<ResponseEntity<T>>`: kiểm soát status/header/body.
- Trả `ResponseEntity<Flux<T>>`: điều khiển status/header trong khi body vẫn streaming.

Đối với POST tạo tài nguyên, `201 Created` cùng `Location` thường diễn đạt rõ hơn việc chỉ trả 200. Không để framework mặc định quyết định status nếu API contract cần quy tắc khác.

### 3.4. Validation và lỗi

Controller có thể dùng `@Valid @RequestBody` để validate DTO. Với lỗi bind/validation, WebFlux có thể phát `WebExchangeBindException`. Dùng `@RestControllerAdvice` và `@ExceptionHandler` để ánh xạ thành schema lỗi thống nhất.

Ví dụ:

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<ApiError> validation(
            WebExchangeBindException exception) {
        // Tạo ApiError với status 400.
    }
}
```

Đây là mã minh họa rút gọn; project hoàn chỉnh ở mục 8 triển khai đầy đủ method và imports. Với lỗi domain như resource không tồn tại, có thể trả `ResponseEntity.notFound()` ngay trong method hoặc dùng exception handler chung. Chọn một chiến lược nhất quán cho toàn API.

## 4. Functional endpoints: RouterFunction và HandlerFunction

### 4.1. Hai thành phần chính

Functional endpoint tách:

- **RouterFunction:** xác định request nào được route tới handler nào.
- **HandlerFunction:** nhận `ServerRequest` và trả `Mono<ServerResponse>`.

Sơ đồ:

```text
HTTP request
    |
    v
RouterFunction
    |
    +-- method + path + headers + predicates
    |
    v
HandlerFunction
    |
    +-- đọc path/query/header/body
    +-- gọi application service
    +-- chọn status/header/content type
    |
    v
Mono<ServerResponse>
```

Router không chứa business logic. Handler không nên tự mở socket hoặc tự serialize JSON; `ServerResponse` phối hợp với WebFlux codecs để tạo response.

### 4.2. Khai báo route bằng Java DSL

```java
@Bean
RouterFunction<ServerResponse> taskRoutes(TaskHandler handler) {
    return RouterFunctions.route()
            .GET("/functional/tasks", handler::list)
            .GET("/functional/tasks/{id}", handler::get)
            .POST("/functional/tasks", handler::create)
            .POST("/functional/tasks/{id}/complete",
                    handler::complete)
            .build();
}
```

Các route được mô tả rõ ràng theo HTTP method và path. Có thể thêm predicate theo query, header, content type, accept header hoặc kết hợp nhiều điều kiện.

Một route function có thể kết hợp nhiều router nhỏ bằng `and`/`andOther` hoặc composition. Khi hệ thống lớn, chia router theo resource/domain giúp tránh một cấu hình route quá dài.

### 4.3. Handler đọc request

`ServerRequest` cung cấp:

- `pathVariable("id")` để đọc path variable.
- `queryParam("q")` để đọc query parameter.
- `headers()` để truy cập request headers.
- `bodyToMono(Type.class)` hoặc `bodyToFlux(Type.class)` để decode body.
- `body(BodyExtractors...)` cho nhu cầu decode nâng cao.

Ví dụ:

```java
public Mono<ServerResponse> get(ServerRequest request) {
    long id = Long.parseLong(request.pathVariable("id"));

    return service.findById(id)
            .flatMap(task -> ServerResponse.ok().bodyValue(task))
            .switchIfEmpty(ServerResponse.notFound().build());
}
```

Functional handler yêu cầu code tự quyết định cách parse và xử lý input. Vì vậy cần xử lý input không hợp lệ rõ ràng; không để `NumberFormatException` vô tình trở thành 500 nếu contract yêu cầu 400.

### 4.4. Tạo response

`ServerResponse` cho phép mô tả status, headers, cookies và body:

```java
return ServerResponse.created(location)
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(task);
```

Các lựa chọn thường dùng:

- `ServerResponse.ok()`: 200.
- `ServerResponse.created(uri)`: 201 và Location.
- `ServerResponse.noContent()`: 204.
- `ServerResponse.badRequest()`: 400.
- `ServerResponse.notFound()`: 404.
- `ServerResponse.status(HttpStatus)`: status tùy chọn.
- `bodyValue(object)`: body đơn.
- `body(publisher, elementClass)`: body reactive stream.

Nếu body là `Flux<T>`, hãy dùng overload nhận Publisher và element type; không `collectList()` vô điều kiện nếu stream lớn hoặc không giới hạn.

### 4.5. Nested routes và predicates

Có thể nhóm route theo path chung:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/functional", builder -> builder
                        .path("/tasks", tasks -> tasks
                                .GET("", handler::list)
                                .GET("/{id}", handler::get)
                                .POST("", handler::create)))
                .build();
```

Đây là ví dụ cấu trúc DSL; cần thêm các route còn lại theo contract. Nested path làm prefix và quan hệ route dễ nhìn hơn. Dù dùng builder chain hay nested router, cần tránh pattern quá rộng đứng trước route cụ thể nếu thứ tự matching làm handler không mong đợi được chọn.

## 5. So sánh hai phong cách

| Tiêu chí | Annotated controller | Functional endpoint |
| --- | --- | --- |
| Khai báo route | Annotation trên class/method | Router DSL hoặc predicate |
| Binding | Argument resolver tự bind | Handler đọc ServerRequest tường minh |
| Response | Return object/Mono/Flux/ResponseEntity | Tạo ServerResponse |
| Validation | `@Valid`, binding result, controller advice | Gọi Validator/kiểm tra input trong handler hoặc dùng helper |
| Error handling | `@RestControllerAdvice`, `@ExceptionHandler` | `onErrorResume`, handler riêng hoặc WebExceptionHandler |
| Group route | `@RequestMapping` ở class | Nested RouterFunction/path predicate |
| Filter | WebFilter, HandlerInterceptor phù hợp | WebFilter hoặc HandlerFilterFunction |
| Độ tường minh | Ít boilerplate, framework tự bind | Nhiều quyết định HTTP hiện rõ trong code |
| Phù hợp | API CRUD phổ biến, team quen annotation | Routing phức tạp, route composition, adapter tường minh |
| Reactive return | Mono/Flux và ResponseEntity | Mono<ServerResponse>, Publisher body |
| Test | WebTestClient | WebTestClient |
| Hiệu năng | Phụ thuộc workload/runtime | Phụ thuộc workload/runtime; không mặc định nhanh hơn |

Không có quy tắc “functional luôn nhanh hơn controller”. Cả hai dùng chung nền tảng reactive HTTP. Khi benchmark, phải dùng cùng service, payload, serialization, server, connection, JVM và load profile. Sự khác biệt thường nằm ở cách tổ chức code và mức độ kiểm soát hơn là một cam kết hiệu năng.

## 6. Validation, lỗi và response contract

### 6.1. DTO là hợp đồng dữ liệu

DTO request:

```java
public record CreateTaskRequest(
        @NotBlank(message = "must not be blank")
        String title) {
}
```

DTO response:

```java
public record TaskView(
        long id,
        String title,
        boolean completed) {
}
```

Lỗi API:

```java
public record ApiError(
        String code,
        String message) {
}
```

Dùng record Java 17 giúp DTO gọn và bất biến. Không đưa entity nội bộ hoặc object chứa dữ liệu nhạy cảm trực tiếp ra response. DTO cũng là nơi định nghĩa versioning và field nào được public.

### 6.2. Controller validation

Trong controller:

```java
@PostMapping
public Mono<ResponseEntity<TaskView>> create(
        @Valid @RequestBody CreateTaskRequest request) {
    // Validation xảy ra trước khi vào business logic.
}
```

Khi validation thất bại, handler method có thể không chạy và WebFlux phát lỗi binding. Controller advice chuyển lỗi đó thành schema `ApiError`.

### 6.3. Functional validation

Trong functional handler, đọc DTO rồi gọi Jakarta Validator:

```java
Set<ConstraintViolation<CreateTaskRequest>> violations =
        validator.validate(requestBody);

if (!violations.isEmpty()) {
    return ServerResponse.badRequest()
            .bodyValue(new ApiError(
                    "VALIDATION_FAILED", "title: must not be blank"));
}
```

Đoạn này minh họa phần validation; cần nằm trong `flatMap` của body publisher để không block hoặc tự subscribe. Với validation đồng bộ trên DTO nhỏ, gọi Validator trực tiếp là hợp lý. Với validation cần truy vấn database/remote service, compose thành reactive pipeline và giới hạn concurrency.

### 6.4. Duy trì cùng error schema

Hai adapter phải trả cùng status, code và message khi input sai. Nếu controller trả `WebExchangeBindException` dưới dạng JSON mặc định còn functional handler tự trả `ApiError`, contract đã khác dù success response giống nhau.

Tạo một error model dùng chung và một quy tắc mapping. Controller dùng advice; functional handler dùng helper hoặc global `WebExceptionHandler` phù hợp. Với lỗi decode JSON malformed, xác định rõ contract 400 và test cả hai adapter.

## 7. Reactive semantics ở cả hai phong cách

### 7.1. Không tự subscribe trong controller/handler

Đúng:

```java
public Mono<TaskView> find(long id) {
    return repository.findById(id);
}
```

Không nên:

```java
public Mono<TaskView> find(long id) {
    repository.findById(id).subscribe();
    return Mono.empty();
}
```

`subscribe()` tự mở subscription riêng, làm framework không còn quản lý đúng lifecycle của công việc. Nó có thể tách Reactor Context, transaction, cancellation và error propagation khỏi request ban đầu.

Controller trả publisher; functional handler compose publisher thành `Mono<ServerResponse>`. Spring WebFlux subscribe khi xử lý HTTP exchange.

### 7.2. Mono, Flux và streaming

- `Mono<T>` biểu diễn tối đa một giá trị hoặc empty/error.
- `Flux<T>` biểu diễn 0..N giá trị theo thời gian.
- `bodyValue` phù hợp cho một object.
- `body(publisher, type)` phù hợp với response stream.
- `ServerSentEvent<T>` và media type `text/event-stream` phù hợp SSE.
- `application/x-ndjson` phù hợp stream JSON line khi client/server hỗ trợ.

Đừng gọi `collectList()` chỉ để dễ serialize nếu response có thể lớn. Nó gom toàn bộ item vào memory trước khi gửi và làm mất lợi ích streaming/backpressure.

### 7.3. Cancellation và client disconnect

Khi client đóng connection, HTTP adapter có thể cancel publisher response. Cả annotated controller lẫn functional handler đều cần xử lý cancellation đúng cách. Nếu upstream là database stream, file, socket hoặc resource tự quản lý, phải giải phóng theo lifecycle reactive. Dùng `usingWhen` cho async cleanup; `doFinally` hữu ích để ghi metric/log nhưng không thay thế publisher cleanup bất đồng bộ.

Không giả định cancel luôn rollback mọi side effect. Nếu transaction đã commit trước khi client disconnect, cancellation không thể hoàn tác commit.

## 8. Project hoàn chỉnh: một service, hai WebFlux adapter

Project dùng Java 17+, Spring Boot 3.3.5, Maven và Spring WebFlux. Hai adapter chạy đồng thời trên hai prefix khác nhau nhưng thực hiện cùng contract. Dữ liệu lưu trong memory nên mất khi process restart; mục tiêu là minh họa routing và test contract.

### 8.1. Cấu trúc thư mục

```text
webflux-two-api-styles/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── ApiApplication.java
    │   │   ├── ApiModels.java
    │   │   ├── TaskService.java
    │   │   ├── TaskController.java
    │   │   ├── TaskHandler.java
    │   │   ├── TaskRoutes.java
    │   │   └── ApiExceptionHandler.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/demo/
            └── ApiContractIntegrationTest.java
```

### 8.2. pom.xml

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
    <artifactId>webflux-two-api-styles</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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

Không thêm `spring-boot-starter-web` vì ứng dụng này chạy WebFlux. Trộn cả MVC và WebFlux starter có thể khiến auto-configuration chọn application type không mong đợi nếu không cấu hình rõ.

### 8.3. application.properties

```properties
spring.application.name=webflux-two-api-styles
server.port=8080
```

### 8.4. ApiApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiApplication.class, args);
    }
}
```

### 8.5. ApiModels.java

```java
package demo;

import jakarta.validation.constraints.NotBlank;

public final class ApiModels {
    private ApiModels() {
    }

    public record CreateTaskRequest(
            @NotBlank(message = "must not be blank")
            String title) {
    }

    public record TaskView(
            long id,
            String title,
            boolean completed) {
    }

    public record ApiError(
            String code,
            String message) {
    }
}
```

### 8.6. TaskService.java

```java
package demo;

import java.util.Comparator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import demo.ApiModels.TaskView;

@Service
public class TaskService {

    private final AtomicLong sequence = new AtomicLong();
    private final ConcurrentMap<Long, TaskView> tasks =
            new ConcurrentHashMap<>();

    public Flux<TaskView> findAll() {
        return Flux.defer(() ->
                Flux.fromIterable(tasks.values().stream()
                        .sorted(Comparator.comparingLong(TaskView::id))
                        .toList()));
    }

    public Mono<TaskView> findById(long id) {
        return Mono.justOrEmpty(tasks.get(id));
    }

    public Mono<TaskView> create(String title) {
        return Mono.fromSupplier(() -> {
            long id = sequence.incrementAndGet();
            TaskView task = new TaskView(id, title, false);
            tasks.put(id, task);
            return task;
        });
    }

    public Mono<TaskView> complete(long id) {
        return Mono.fromSupplier(() -> {
            TaskView current = tasks.get(id);
            if (current == null) {
                return null; // Mono.fromSupplier(null) becomes empty.
            }

            TaskView updated = new TaskView(
                    id, current.title(), true);
            tasks.put(id, updated);
            return updated;
        });
    }
}
```

`ConcurrentHashMap` và `AtomicLong` cho phép demo chịu được nhiều request đồng thời ở mức store đơn giản. Đây không phải repository có transaction hoặc persistence bền vững. `Mono.fromSupplier` lazy: task chỉ được tạo khi request publisher được subscribe.

### 8.7. TaskController.java — annotated adapter

```java
package demo;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import demo.ApiModels.CreateTaskRequest;
import demo.ApiModels.TaskView;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/controller/tasks")
class TaskController {

    private final TaskService service;

    TaskController(TaskService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<TaskView> list() {
        return service.findAll();
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<TaskView>> get(
            @PathVariable long id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(
                        ResponseEntity.<TaskView>notFound().build());
    }

    @PostMapping
    public Mono<ResponseEntity<TaskView>> create(
            @Valid @RequestBody CreateTaskRequest request) {
        return service.create(request.title())
                .map(task -> ResponseEntity
                        .created(URI.create(
                                "/controller/tasks/" + task.id()))
                        .body(task));
    }

    @PostMapping("/{id}/complete")
    public Mono<ResponseEntity<TaskView>> complete(
            @PathVariable long id) {
        return service.complete(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(
                        ResponseEntity.<TaskView>notFound().build());
    }
}
```

Controller method không tự subscribe. Spring WebFlux xử lý `Flux`/`Mono` và ghi response. `ResponseEntity` cho phép định nghĩa 201 và Location rõ ràng.

### 8.8. ApiExceptionHandler.java — validation error cho controller

```java
package demo;

import java.util.stream.Collectors;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import demo.ApiModels.ApiError;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiError> validation(
            WebExchangeBindException exception) {
        String message = exception.getFieldErrors().stream()
                .map(error -> error.getField()
                        + ": " + error.getDefaultMessage())
                .sorted()
                .collect(Collectors.joining("; "));

        return ResponseEntity.badRequest().body(
                new ApiError("VALIDATION_FAILED", message));
    }
}
```

`@RestControllerAdvice` xử lý lỗi validation của annotated controller. Functional handler trong bài tự validate và tạo cùng `ApiError` vì hai kiểu handler có cơ chế xử lý lỗi ở biên khác nhau.

### 8.9. TaskHandler.java — functional handler

```java
package demo;

import java.net.URI;
import java.util.Set;
import java.util.function.LongFunction;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import demo.ApiModels.ApiError;
import demo.ApiModels.CreateTaskRequest;
import demo.ApiModels.TaskView;
import reactor.core.publisher.Mono;

@Component
class TaskHandler {

    private final TaskService service;
    private final Validator validator;

    TaskHandler(TaskService service, Validator validator) {
        this.service = service;
        this.validator = validator;
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(service.findAll(), TaskView.class);
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        return withId(request, id ->
                service.findById(id)
                        .flatMap(task -> ServerResponse.ok()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(task))
                        .switchIfEmpty(ServerResponse.notFound().build()));
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateTaskRequest.class)
                .flatMap(body -> {
                    Set<ConstraintViolation<CreateTaskRequest>> violations =
                            validator.validate(body);

                    if (!violations.isEmpty()) {
                        String message = violations.stream()
                                .map(v -> v.getPropertyPath()
                                        + ": " + v.getMessage())
                                .sorted()
                                .collect(Collectors.joining("; "));

                        return ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new ApiError(
                                        "VALIDATION_FAILED", message));
                    }

                    return service.create(body.title())
                            .flatMap(task -> ServerResponse
                                    .created(URI.create(
                                            "/functional/tasks/" + task.id()))
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .bodyValue(task));
                })
                .switchIfEmpty(ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(new ApiError(
                                "VALIDATION_FAILED",
                                "request body is required")));
    }

    public Mono<ServerResponse> complete(ServerRequest request) {
        return withId(request, id ->
                service.complete(id)
                        .flatMap(task -> ServerResponse.ok()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(task))
                        .switchIfEmpty(ServerResponse.notFound().build()));
    }

    private Mono<ServerResponse> withId(
            ServerRequest request,
            LongFunction<Mono<ServerResponse>> action) {
        try {
            long id = Long.parseLong(request.pathVariable("id"));
            return action.apply(id);
        } catch (NumberFormatException exception) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(new ApiError(
                            "INVALID_ID", "id must be a number"));
        }
    }
}
```

Các điểm quan trọng:

- `ServerRequest` được đọc trực tiếp thay cho annotation argument binding.
- Validator được inject từ Bean Validation provider do starter validation cấu hình.
- Validation error trả cùng code/message contract với controller.
- `withId` xử lý id không phải số thành 400, tránh lỗi parse trở thành 500.
- Service chỉ được gọi trong publisher chain; không có nested `subscribe()`.

### 8.10. TaskRoutes.java — router function

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class TaskRoutes {

    @Bean
    RouterFunction<ServerResponse> taskRoutes(TaskHandler handler) {
        return RouterFunctions.route()
                .GET("/functional/tasks", handler::list)
                .GET("/functional/tasks/{id}", handler::get)
                .POST("/functional/tasks", handler::create)
                .POST("/functional/tasks/{id}/complete",
                        handler::complete)
                .build();
    }
}
```

Các route functional chạy song song với controller vì prefix khác nhau. Router không thực hiện business logic; nó chỉ nối request predicate tới handler.

## 9. Contract tests: kiểm tra hai adapter bằng cùng một bộ kỳ vọng

`WebTestClient` có thể test controller bind trực tiếp hoặc gọi server thật. Bài này dùng `RANDOM_PORT` để cả hai adapter đi qua HTTP stack và codec thật trong tiến trình test.

### 9.1. ApiContractIntegrationTest.java

```java
package demo;

import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import demo.ApiModels.ApiError;
import demo.ApiModels.CreateTaskRequest;
import demo.ApiModels.TaskView;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ApiContractIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void bothStylesHonorTheSameSuccessContract() {
        assertSuccessContract("/controller");
        assertSuccessContract("/functional");
    }

    private void assertSuccessContract(String prefix) {
        AtomicLong id = new AtomicLong();

        client.post()
                .uri(prefix + "/tasks")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateTaskRequest("Prepare release"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists(HttpHeaders.LOCATION)
                .expectBody(TaskView.class)
                .value(task -> {
                    assertTrue(task.id() > 0);
                    assertEquals("Prepare release", task.title());
                    assertFalse(task.completed());
                    id.set(task.id());
                });

        long taskId = id.get();

        client.get()
                .uri(prefix + "/tasks/{id}", taskId)
                .exchange()
                .expectStatus().isOk()
                .expectBody(TaskView.class)
                .value(task -> {
                    assertEquals(taskId, task.id());
                    assertEquals("Prepare release", task.title());
                    assertFalse(task.completed());
                });

        client.post()
                .uri(prefix + "/tasks/{id}/complete", taskId)
                .exchange()
                .expectStatus().isOk()
                .expectBody(TaskView.class)
                .value(task -> {
                    assertEquals(taskId, task.id());
                    assertTrue(task.completed());
                });

        client.get()
                .uri(prefix + "/tasks")
                .exchange()
                .expectStatus().isOk()
                .expectBodyList(TaskView.class)
                .value(tasks -> assertTrue(
                        tasks.stream().anyMatch(task ->
                                task.id() == taskId
                                && task.completed())));
    }

    @Test
    void bothStylesReturnTheSameValidationError() {
        for (String prefix : List.of("/controller", "/functional")) {
            client.post()
                    .uri(prefix + "/tasks")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(new CreateTaskRequest(" "))
                    .exchange()
                    .expectStatus().isBadRequest()
                    .expectBody(ApiError.class)
                    .value(error -> {
                        assertEquals(
                                "VALIDATION_FAILED", error.code());
                        assertTrue(error.message().contains("title"));
                        assertTrue(error.message()
                                .contains("must not be blank"));
                    });
        }
    }

    @Test
    void bothStylesReturn404ForMissingTask() {
        for (String prefix : List.of("/controller", "/functional")) {
            client.get()
                    .uri(prefix + "/tasks/999999")
                    .exchange()
                    .expectStatus().isNotFound();

            client.post()
                    .uri(prefix + "/tasks/999999/complete")
                    .exchange()
                    .expectStatus().isNotFound();
        }
    }

    @Test
    void functionalEndpointRejectsNonNumericId() {
        client.get()
                .uri("/functional/tasks/not-a-number")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(ApiError.class)
                .value(error ->
                        assertEquals("INVALID_ID", error.code()));
    }
}
```

Bộ test kiểm tra:

1. Cùng một luồng tạo → đọc → hoàn tất → liệt kê trên cả hai prefix.
2. Cùng status 201, Location header và JSON response.
3. Cùng schema validation error 400.
4. Cùng hành vi 404 khi resource không tồn tại.
5. Functional handler trả 400 rõ ràng khi id không phải số.

Test này dùng server HTTP thật trên loopback với cổng ngẫu nhiên. Nó kiểm tra route, binding, validation, codec và response contract; nó chưa kiểm tra database thật, TLS production hoặc tải đồng thời lớn.

### 9.2. Chạy test

Tại thư mục project:

```bash
mvn test
```

Với JDK 17+, Maven và dependency tải được, kỳ vọng **4 test methods thành công, 0 failures, 0 errors**. Đây là kết quả dự kiến từ assertion trong source, không phải tuyên bố đã thực thi build trong môi trường này.

## 10. Functional filters, WebFilter và cross-cutting concerns

Functional endpoint có `HandlerFilterFunction` để bao quanh handler. Ví dụ ghi thời gian xử lý:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> timing =
        (request, next) -> {
            long started = System.nanoTime();

            return next.handle(request)
                    .doFinally(signal -> {
                        long elapsed = System.nanoTime() - started;
                        // Ghi metric: route, signal và elapsed.
                    });
        };
```

Đây là mã minh họa filter, cần import `HandlerFilterFunction` và `SignalType` nếu sử dụng. Có thể gắn filter vào router bằng `.filter(timing)` trước `.build()`. Không ghi raw body hoặc dữ liệu nhạy cảm vào log.

`WebFilter` hoạt động ở tầng WebFlux WebHandler chain, có thể áp dụng cho cả annotated controller và functional endpoint. Nếu cross-cutting concern phải áp dụng toàn ứng dụng (trace ID, security, CORS, logging, metrics), global WebFilter thường là lựa chọn hợp lý. `HandlerFilterFunction` phù hợp khi muốn giới hạn filter cho một router/nhóm functional route.

Không nhầm `HandlerFilterFunction` với Servlet Filter; ứng dụng WebFlux không nhất thiết có Servlet container.

## 11. Content negotiation và streaming

Cả hai phong cách sử dụng cùng WebFlux codecs và content negotiation:

- `Accept` quyết định representation client muốn nhận.
- `Content-Type` mô tả representation của request/response body.
- Jackson codec có thể serialize record/DTO thành JSON.
- `Flux<T>` có thể được encode thành JSON array hoặc streaming format tùy media type và writer.
- `text/event-stream` thường dùng cho SSE.
- `application/x-ndjson` có thể dùng cho JSON records theo dòng.

Annotated controller có thể khai báo `produces`/`consumes` ngay trên mapping. Functional router có thể thêm predicate `accept`/`contentType` hoặc đặt content type khi tạo ServerResponse.

Ví dụ controller:

```java
@GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(index -> ServerSentEvent.builder(
                    "tick-" + index).build());
}
```

Functional handler có thể tạo response streaming:

```java
return ServerResponse.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(events, ServerSentEvent.class);
```

Đây là các snippet minh họa; cần định nghĩa source `events` và imports. Không gọi `collectList()` trên stream vô hạn. Hãy xử lý cancel khi client disconnect và giải phóng tài nguyên.

## 12. Khi nào nên chọn phong cách nào?

### Chọn annotated controller khi:

- API chủ yếu là CRUD/REST thông thường.
- Muốn argument binding, validation annotation và method mapping dễ đọc.
- Team đã quen controller/advice và muốn tận dụng conventions.
- Phần lớn method có cấu trúc tương tự nhau.

### Chọn functional endpoint khi:

- Muốn nhìn route table tường minh và composition route theo module.
- Có nhiều predicate theo method/path/header/content type.
- Muốn kiểm soát cách đọc request và xây response ở từng handler.
- API gateway/protocol adapter có route logic riêng biệt và rõ ràng.

### Dùng kết hợp khi:

Spring WebFlux cho phép controller và functional routes cùng tồn tại. Một module có thể dùng controller cho CRUD, functional route cho webhook hoặc protocol-specific endpoint. Cần tránh đăng ký cùng một method/path ở cả hai nơi nếu không có chủ ý; route conflict làm behavior khó đoán và test khó đọc.

### Tiêu chí lựa chọn thực tế

Không quyết định bằng số dòng code hoặc giả định performance. Hãy đánh giá:

- Độ dễ đọc và onboarding.
- Cách áp dụng security/validation/error mapping.
- Mức độ phức tạp của route.
- Khả năng test contract.
- Quy ước codebase hiện tại.
- Khả năng quan sát và maintain.
- Nhu cầu streaming và lifecycle.

Nếu hai adapter cần cùng một business behavior, giữ chung service và test cùng contract để việc đổi phong cách không tạo regression.

## 13. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ functional endpoint là Spring MVC functional view | Chọn sai API và runtime | Dùng `RouterFunction`/`ServerRequest`/`ServerResponse` của WebFlux. |
| Nghĩ controller WebFlux là MVC controller | Trộn dependency và kỳ vọng blocking | Dùng WebFlux starter và reactive return types. |
| Đăng ký cùng route trong controller và RouterFunction | Route conflict hoặc handler được chọn ngoài dự kiến | Dùng prefix/profile hoặc chỉ bật một adapter trên canonical path. |
| Đặt business logic trong router | Khó test và tái sử dụng | Router chỉ định tuyến; handler gọi service. |
| Đặt business logic trùng trong hai handler | Behavior drift | Tách service/application layer dùng chung. |
| Functional handler quên parse input | NumberFormatException có thể thành 500 | Map lỗi parse thành 400. |
| Controller và functional trả schema lỗi khác nhau | Client phải xử lý hai contract | Dùng ApiError chung và test cả hai. |
| Quên Location khi tạo tài nguyên | Client không có URI chuẩn để truy cập resource | Trả 201 + Location theo contract. |
| Gọi subscribe trong handler | Tách lifecycle, mất cancellation/error context | Return và compose Mono/Flux. |
| Block trong WebFlux | Chặn event-loop | Dùng reactive API hoặc scheduler phù hợp cho blocking. |
| collectList trên stream lớn/vô hạn | Tăng memory, mất streaming | Trả Publisher body phù hợp. |
| Chỉ unit test handler | Bỏ sót routing/codec/status/header | Thêm WebTestClient integration test. |
| Chỉ test success | Bỏ sót 400/404/error contract | Test invalid input, missing resource và lỗi decode. |
| Cho rằng functional luôn nhanh hơn | Kết luận không có dữ liệu | Benchmark cùng workload và môi trường nếu hiệu năng quan trọng. |
| Dùng WebFilter thay HandlerFilterFunction mà không cân nhắc scope | Filter áp dụng rộng hơn dự kiến | Chọn global hay router-local theo trách nhiệm. |
| Không kiểm thử route conflict | Production có thể gọi nhầm handler | Test method/path của tất cả adapter đang bật. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Hai cách tạo endpoint của Spring WebFlux là gì?  
**Đáp án:** Annotated controller và functional endpoint với RouterFunction/HandlerFunction.

**Câu 2.** Controller WebFlux có thể trả Flux không?  
**Đáp án:** Có. Framework xử lý Publisher và serialize body theo codec/media type.

**Câu 3.** RouterFunction làm nhiệm vụ gì?  
**Đáp án:** Match request predicate (method/path/header/content type...) với HandlerFunction.

**Câu 4.** HandlerFunction nhận và trả gì?  
**Đáp án:** Nhận ServerRequest và trả Mono<ServerResponse>.

**Câu 5.** Functional handler lấy path variable như thế nào?  
**Đáp án:** Dùng `request.pathVariable("id")` rồi tự parse/validate kiểu dữ liệu.

**Câu 6.** Vì sao cần service dùng chung giữa hai adapter?  
**Đáp án:** Tránh lặp business rule và giữ behavior nhất quán khi đổi cách khai báo HTTP.

**Câu 7.** Controller validation error thường được xử lý ở đâu?  
**Đáp án:** WebExchangeBindException có thể được ánh xạ qua RestControllerAdvice/ExceptionHandler.

**Câu 8.** Functional handler validate DTO như thế nào?  
**Đáp án:** Decode body thành DTO, gọi Jakarta Validator hoặc helper, rồi trả status/error contract phù hợp.

**Câu 9.** Hai adapter có thể cùng chạy trong một app không?  
**Đáp án:** Có, miễn route không xung đột; bài demo dùng hai prefix riêng.

**Câu 10.** Functional endpoint có luôn nhanh hơn controller không?  
**Đáp án:** Không. Cả hai dùng cùng reactive runtime; cần benchmark cùng điều kiện để kết luận.

**Câu 11.** Khi nào dùng WebFilter thay HandlerFilterFunction?  
**Đáp án:** WebFilter cho cross-cutting concern toàn WebFlux chain; HandlerFilterFunction cho nhóm functional routes.

**Câu 12.** Vì sao không tự subscribe trong handler?  
**Đáp án:** Vì sẽ tách lifecycle, cancellation, context và error propagation khỏi HTTP request hiện tại.

## 15. Ghi nhớ

- Annotated controller mô tả endpoint bằng annotation; functional endpoint tách route predicate và handler.
- Cả hai đều là WebFlux, hỗ trợ Mono/Flux, codec, non-blocking I/O và cancellation.
- RouterFunction định tuyến; HandlerFunction đọc ServerRequest và tạo ServerResponse.
- Tách DTO, validation, business service và persistence để hai adapter dùng chung logic.
- Giữ contract thống nhất về method/path, status, Location, content type, JSON và error schema.
- Dùng WebTestClient để kiểm tra cả hai adapter qua cùng bộ contract test.
- Không gọi subscribe/block trong handler, không gom stream vô hạn vào list.
- Chọn phong cách theo độ rõ ràng, tổ chức route, khả năng maintain và conventions; không mặc định functional nhanh hơn.

## Tài liệu tham khảo

1. [Spring Framework – Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): request mapping, argument binding, return values và validation.
2. [Spring Framework – Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): RouterFunction, HandlerFunction, ServerRequest và ServerResponse.
3. [Spring Framework – WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): validation trong WebFlux controller.
4. [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): test controller và HTTP server.
5. [Spring Boot 3.3 – Testing Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): RANDOM_PORT và WebTestClient integration.
6. [Project Reactor – Core Reference](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, scheduling, cancellation và backpressure.
7. [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/3.0/): constraint annotations và Validator API.

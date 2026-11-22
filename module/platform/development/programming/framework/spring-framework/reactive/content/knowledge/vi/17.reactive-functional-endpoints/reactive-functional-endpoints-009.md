# So sánh endpoint hàm với controller cho cùng một hợp đồng HTTP trong Spring WebFlux

> **Module:** Spring Framework – reactive · **Chủ đề cha:** Endpoint hàm. Bài học so sánh hai cách xây dựng HTTP API của WebFlux: annotated controller (`@RestController`, `@GetMapping`, `@PostMapping`) và functional endpoint (`RouterFunction`, `HandlerFunction`, `ServerRequest`, `ServerResponse`). Hai cách sẽ dùng cùng domain service và cùng HTTP contract để làm rõ phần nào thay đổi theo mô hình lập trình và phần nào vẫn thuộc nền tảng WebFlux chung.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích annotated controller và WebFlux.fn cùng chạy trên Reactive Core, `DispatcherHandler`, HTTP server, codec và WebFilter chain.
2. Ánh xạ một hợp đồng HTTP sang `@RequestMapping` hoặc `RouterFunction`/`RequestPredicate`.
3. Viết cùng một handler bằng controller method và `HandlerFunction<ServerResponse>`.
4. So sánh cách lấy path/query/header/body, validation, status, headers, response body, lỗi và streaming.
5. Phân biệt phạm vi của `@ControllerAdvice`, `HandlerFilterFunction`, `WebFilter` và Spring Security.
6. Hiểu route order của functional endpoint, route specificity của annotated mapping và rủi ro route shadowing.
7. Kiểm chứng hai implementation có cùng observable contract bằng HTTP integration tests.
8. Chọn mô hình theo cấu trúc module, độ phức tạp của binding và cách tổ chức team.

**Nguyên tắc so sánh:** cùng một hợp đồng HTTP nghĩa là client nhìn thấy cùng method, status, headers, content type, body schema, error schema và semantics khi không có dữ liệu. Tên class, annotation hay lambda không phải một phần của HTTP contract.

## 2. Hai mô hình, một nền tảng WebFlux

Spring WebFlux cung cấp hai cách mô tả endpoint:

- **Annotated controller:** khai báo ý định bằng annotation. Spring tìm method theo mapping, resolve tham số, gọi method và diễn giải return value.
- **Functional endpoint (WebFlux.fn):** khai báo route bằng `RouterFunction`, xử lý request bằng `HandlerFunction`; ứng dụng chủ động đọc `ServerRequest` và xây dựng `ServerResponse`.

Cả hai dùng Reactive Streams/Reactor, cùng server như Reactor Netty, cùng `WebFilter`, Spring Security, codecs, `HttpMessageReader`/`HttpMessageWriter`, backpressure và cancellation.

~~~text
                         HTTP request
                              |
                         HttpHandler
                              |
                    WebFilter / Security
                              |
                      DispatcherHandler
                              |
                 +------------+-------------+
                 |                          |
        Annotated mapping            RouterFunctionMapping
                 |                          |
       RequestMappingHandlerMapping     RouterFunction
                 |                          |
       RequestMappingHandlerAdapter    HandlerFunctionAdapter
                 |                          |
       Controller method               HandlerFunction
                 |                          |
         HandlerResult                Mono<ServerResponse>
                 |                          |
       Result handlers                ServerResponseResultHandler
                 |                          |
                 +------------+-------------+
                              |
                   HTTP response + codecs
~~~

Functional endpoint không phải một HTTP server riêng và không bỏ qua `DispatcherHandler` trong cấu hình WebFlux thông thường. `RouterFunctionMapping`, `HandlerFunctionAdapter` và `ServerResponseResultHandler` nối WebFlux.fn vào cùng vòng đời dispatch. Có thể dùng hai mô hình trong một ứng dụng nếu route không xung đột.

## 3. Định nghĩa hợp đồng HTTP trước khi so sánh

Ta xây dựng API quản lý `Item` với ba thao tác:

| Method | Path sau prefix | Request | Thành công | Không tìm thấy / lỗi |
| --- | --- | --- | --- | --- |
| GET | `/items/{id}` | Không body | 200 + `Item` JSON | 404, body rỗng |
| POST | `/items` | `{"name":"Keyboard"}` | 201 + `Location` + `Item` JSON | 400 + ProblemDetail nếu name trống |
| DELETE | `/items/{id}` | Không body | 204, body rỗng | 404, body rỗng |

Để chạy cả hai implementation trong cùng một server mà không đăng ký hai handler cho cùng path, demo dùng hai prefix:

- Annotated: `/api/annotated/items`
- Functional: `/api/functional/items`

Prefix khác nhau chỉ để phân biệt implementation trong demo. Phần path còn lại, status, headers, schema JSON, thông điệp lỗi và quy tắc dữ liệu giống nhau.

**GET thành công:**

~~~http
GET /api/annotated/items/42
Accept: application/json
~~~

và:

~~~http
GET /api/functional/items/42
Accept: application/json
~~~

Cả hai trả cùng schema:

~~~json
{
  "id": "42",
  "name": "Seed item"
}
~~~

Nếu id không tồn tại, cả hai trả `404 Not Found` và body rỗng.

**POST thành công:**

~~~http
POST /api/functional/items
Content-Type: application/json
Accept: application/json

{"name":"Keyboard"}
~~~

Cả hai trả status 201, header `Location` trỏ tới resource vừa tạo, content type JSON và body chứa cùng `id`/`name`. ID tăng dần trong ví dụ nên giá trị cụ thể thay đổi theo thứ tự request; ID trong body phải khớp với ID trong Location.

**POST không hợp lệ:** `{"name":" "}` phải trả `400 Bad Request` và ProblemDetail với `title`, `detail`, `status` cùng `code=ITEM_NAME_INVALID`. Client không cần biết lỗi được chuyển thành response bởi `@RestControllerAdvice` hay functional route filter.

## 4. Giữ domain service giống nhau

Để so sánh công bằng, hai endpoint dùng chung:
- DTO `Item` và `CreateItemRequest`.
- `ItemService` chứa quy tắc kiểm tra tên, tạo ID, đọc và xóa item.
- Một factory tạo ProblemDetail.
- Cùng JSON codecs và HTTP server.
- Cùng bộ test HTTP kiểm tra status/header/body.

Chỉ phần **định tuyến, lấy dữ liệu request, gọi handler và tạo response** được biểu diễn theo từng mô hình. Nếu mỗi implementation tự viết validation/service riêng, kết quả khác nhau có thể đến từ business logic chứ không phải mô hình endpoint.

## 5. Annotated controller diễn đạt hợp đồng

Một controller thường dùng:
- `@RestController` để ghi return value vào body.
- `@RequestMapping` để khai báo prefix.
- `@GetMapping`, `@PostMapping`, `@DeleteMapping` để khai báo HTTP method/path.
- `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody` để bind request.
- `ResponseEntity<T>` để điều khiển status, headers và body.
- `@ExceptionHandler`/`@RestControllerAdvice` để chuyển lỗi thành response.

Ví dụ GET:

~~~java
@GetMapping("/{id}")
Mono<ResponseEntity<Item>> get(@PathVariable String id) {
    return service.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().<Item>build());
}
~~~

Method tập trung vào tham số và kết quả nghiệp vụ. Spring resolve path variable, gọi method và dùng return-value handler ghi response.

Annotation giúp code ngắn, dễ đọc khi endpoint theo mẫu CRUD/REST phổ biến và có nhiều tham số được framework hỗ trợ. Đổi lại, một phần hành vi nằm trong annotation, argument resolver, validation, advice và cấu hình WebFlux; người đọc cần hiểu quy ước framework.

## 6. Functional endpoint diễn đạt cùng hợp đồng

WebFlux.fn dùng hai hợp đồng chính:

~~~java
@FunctionalInterface
public interface HandlerFunction<T extends ServerResponse> {
    Mono<T> handle(ServerRequest request);
}
~~~

`HandlerFunction` nhận `ServerRequest` và trả response bất đồng bộ, thường là `Mono<ServerResponse>`.

~~~java
@FunctionalInterface
public interface RouterFunction<T extends ServerResponse> {
    Mono<HandlerFunction<T>> route(ServerRequest request);
}
~~~

`RouterFunction` kiểm tra request và trả handler phù hợp; nếu không match thì hoàn tất rỗng để router tiếp theo có cơ hội xử lý.

Ví dụ GET tương đương:

~~~java
Mono<ServerResponse> get(ServerRequest request) {
    String id = request.pathVariable("id");

    return service.findById(id)
        .flatMap(item -> ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(item))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

Handler đọc path variable trực tiếp từ `ServerRequest`, gọi service và xây dựng `ServerResponse`. Functional endpoint làm luồng xử lý tường minh hơn, đặc biệt khi request có nhiều nhánh hoặc route được composition theo module.

## 7. Mapping: annotation và RouterFunction

| Khía cạnh | Annotated controller | Functional endpoint |
| --- | --- | --- |
| Định tuyến | `@RequestMapping`, `@GetMapping`, ... | `RouterFunction` và `RequestPredicate` |
| Match HTTP method/path | Framework phân tích mapping metadata | Predicate do router builder tạo |
| Path variable | `@PathVariable` | `request.pathVariable("id")` |
| Query parameter | `@RequestParam` | `request.queryParam("page")` |
| Header | `@RequestHeader` | `request.headers().firstHeader("X-...")` |
| Content-Type / Accept | `consumes`, `produces` | `contentType(...)`, `accept(...)` predicates |
| Thứ tự route | Framework chọn mapping cụ thể nhất; mapping mơ hồ có thể lỗi | RouterFunction được đánh giá theo thứ tự composition |
| Nhóm route | Controller class + base mapping | Builder `.path(...)`, `.nest(...)`, `.and(...)` |

### 7.1. Annotated mapping

~~~java
@RestController
@RequestMapping("/api/annotated/items")
class ItemController {

    @GetMapping("/{id}")
    Mono<Item> get(@PathVariable String id) {
        return service.findById(id);
    }

    @GetMapping(params = "active=true")
    Flux<Item> active() {
        return service.findActive();
    }
}
~~~

Framework tạo mapping từ annotation, điều kiện method/path/query/header/media type. Với mapping gần nhau, Spring xét specificity và phát hiện trường hợp mơ hồ.

### 7.2. Functional mapping

~~~java
@Bean
RouterFunction<ServerResponse> itemRoutes(ItemHandler handler) {
    return RouterFunctions.route()
        .path("/api/functional/items", builder -> builder
            .GET("/{id}", handler::get)
            .GET(RequestPredicates.queryParam("active", "true"),
                handler::active))
        .build();
}
~~~

Router builder cho phép ghép route và nhóm chúng theo path/predicate. Route được đánh giá theo thứ tự composition: đặt route cụ thể trước route tổng quát để tránh route tổng quát bắt request trước.

**Khác biệt quan trọng:** annotated mapping thường chọn mapping phù hợp cụ thể nhất; functional routing làm rõ thứ tự các router được ghép. Khi refactor, phải kiểm tra route overlap, thứ tự `and`/`andRoute`, predicate `nest` và fallback.

## 8. Lấy request data và đọc body

Annotated controller bind request vào tham số:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
Mono<Item> create(@RequestBody Mono<CreateItemRequest> body) {
    return body.flatMap(service::create);
}
~~~

Functional handler đọc request tường minh:

~~~java
Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateItemRequest.class)
        .flatMap(service::create)
        .flatMap(item -> ServerResponse.created(
                URI.create("/api/functional/items/" + item.id()))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(item));
}
~~~

Cả hai dùng message reader/codecs để decode JSON. `@RequestBody Mono<T>` và `ServerRequest.bodyToMono(T.class)` đều là reactive body extraction; chúng không bắt buộc đọc toàn bộ body đồng bộ trước khi method chạy.

Annotated model cung cấp resolver cho path variable, query parameter, header, cookie, principal, session, exchange, validation, model attribute và request body. Functional model gom thông tin trong `ServerRequest`; code chủ động gọi `pathVariable`, `queryParam`, `headers`, `bodyToMono`, `bodyToFlux`, `principal`, `session` hoặc `exchange`.

Với endpoint có vài tham số chuẩn, annotation thường ngắn. Với pipeline đọc body, kiểm tra nhiều predicate và rẽ nhánh, việc gọi tường minh có thể làm thứ tự xử lý dễ theo dõi hơn.


## 9. Response: ResponseEntity và ServerResponse

Hai mô hình đều có thể phát ra cùng HTTP status, headers và body.

### 9.1. ResponseEntity trong controller

~~~java
Mono<ResponseEntity<Item>> find(String id) {
    return service.findById(id)
        .map(item -> ResponseEntity.ok()
            .header("X-Api-Version", "1")
            .body(item))
        .defaultIfEmpty(ResponseEntity.notFound().<Item>build());
}
~~~

`ResponseEntity` phù hợp với method return value và các dạng reactive lồng nhau như `Mono<ResponseEntity<T>>`, `ResponseEntity<Mono<T>>`, `ResponseEntity<Flux<T>>`.

### 9.2. ServerResponse trong functional handler

~~~java
Mono<ServerResponse> find(ServerRequest request) {
    return service.findById(request.pathVariable("id"))
        .flatMap(item -> ServerResponse.ok()
            .header("X-Api-Version", "1")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(item))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

`ServerResponse` là abstraction response của WebFlux.fn. Các builder `ok`, `created`, `accepted`, `noContent`, `notFound`, `badRequest`, `status` giúp tạo status và header. `bodyValue` nhận object đã có; `body` nhận Publisher/BodyInserter khi body bất đồng bộ hoặc streaming.

### 9.3. Bảng ánh xạ status/header/body

| Ý định | Controller | Functional |
| --- | --- | --- |
| 200 + body | `ResponseEntity.ok(body)` | `ServerResponse.ok().bodyValue(body)` |
| 201 + Location | `ResponseEntity.created(uri).body(body)` | `ServerResponse.created(uri).bodyValue(body)` |
| 202 | `ResponseEntity.accepted().build()` | `ServerResponse.accepted().build()` |
| 204 | `ResponseEntity.noContent().build()` | `ServerResponse.noContent().build()` |
| 400 | `ResponseEntity.badRequest().body(error)` | `ServerResponse.badRequest().bodyValue(error)` |
| 404 | `ResponseEntity.notFound().build()` | `ServerResponse.notFound().build()` |
| Header tùy chỉnh | `ResponseEntity.ok().header(...).body(...)` | `ServerResponse.ok().header(...).bodyValue(...)` |

Trong cả hai mô hình, status/header cần được quyết định trước khi response commit. Nếu body stream bắt đầu ghi rồi mới phát lỗi, server không thể thay status đã gửi.

## 10. Validation và lỗi: khác cách gắn, cùng contract

### 10.1. Annotated controller

Annotated controller có thể dùng Bean Validation qua `@Valid`/`@Validated` và xử lý lỗi bằng `@ExceptionHandler` hoặc `@RestControllerAdvice`.

~~~java
@PostMapping
Mono<ResponseEntity<Item>> create(
        @Valid @RequestBody Mono<CreateItemRequest> request) {
    return request.flatMap(service::create)
        .map(item -> ResponseEntity
            .created(URI.create("/api/annotated/items/" + item.id()))
            .body(item));
}
~~~

Ví dụ trên cần validation provider trên classpath và DTO có constraint như `@NotBlank`. Lỗi resolve/validate body được chuyển qua exception handling của annotated controller.

### 10.2. Functional endpoint

Functional handler nhận một `ServerRequest`, vì vậy ứng dụng chủ động gọi `Validator`, validation service hoặc domain constructor sau khi decode body. Ví dụ:

~~~java
Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateItemRequest.class)
        .flatMap(service::create)
        .flatMap(item -> ServerResponse.created(
                URI.create("/api/functional/items/" + item.id()))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(item));
}
~~~

Quy tắc validation nên đặt ở tầng dùng chung nếu hai kiểu endpoint phải giữ cùng contract.

### 10.3. Exception handling khác phạm vi

- `@RestControllerAdvice`/`@ControllerAdvice` gắn với annotated controller invocation và lỗi return value của chúng.
- `HandlerFilterFunction` bao quanh các route function được composition vào router builder; có thể dùng `onErrorResume` để chuyển exception thành `ServerResponse`.
- `WebExceptionHandler` chạy ở WebHandler chain và có thể xử lý lỗi ở phạm vi rộng hơn, gồm filter/handler chain.
- `WebFilter` phù hợp logic xuyên suốt request như correlation ID, authentication/authorization, metrics và CORS; nó không thay thế mọi exception mapping.

Một `@ControllerAdvice` không tự động là cơ chế xử lý lỗi cho mọi `HandlerFunction`. Nếu hai mô hình phải có cùng ProblemDetail, hãy chia sẻ factory/mapper tạo error body và gọi nó từ `@ExceptionHandler` lẫn functional filter, hoặc dùng một `WebExceptionHandler` chung có chủ đích.

### 10.4. Ví dụ cùng ProblemDetail

~~~java
final class ApiProblems {
    private ApiProblems() {}

    static ProblemDetail invalidName(IllegalArgumentException error) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, error.getMessage());
        problem.setTitle("Invalid item");
        problem.setProperty("code", "ITEM_NAME_INVALID");
        return problem;
    }
}
~~~

Annotated side:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {
    @ExceptionHandler(IllegalArgumentException.class)
    ProblemDetail invalidName(IllegalArgumentException error) {
        return ApiProblems.invalidName(error);
    }
}
~~~

Functional side:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .POST("/api/functional/items", handler::create)
    .filter((request, next) -> next.handle(request)
        .onErrorResume(IllegalArgumentException.class, error ->
            ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .bodyValue(ApiProblems.invalidName(error))))
    .build();
~~~

Cả hai trả status 400 và cùng cấu trúc ProblemDetail. Functional filter chỉ bao quanh router mà nó được gắn vào; không tự áp dụng lên route bean khác nếu không composition.

## 11. Filters, cross-cutting concerns và bảo mật

### 11.1. WebFilter dùng chung

`WebFilter` bao quanh WebHandler chain, vì vậy có thể áp dụng cho cả annotated controller và functional route. Ví dụ request ID:

~~~java
@Component
class RequestIdFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {
        String requestId = UUID.randomUUID().toString();
        exchange.getResponse().getHeaders()
            .set("X-Request-Id", requestId);
        return chain.filter(exchange);
    }
}
~~~

Đây là fragment component. Production nên lấy hoặc kiểm tra request ID từ header tin cậy, tránh coi một chuỗi tùy ý là identity đã xác minh.

### 11.2. HandlerFilterFunction riêng cho WebFlux.fn

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/api/functional/items/{id}", handler::get)
    .filter((request, next) -> {
        if (!accessAllowed(request)) {
            return ServerResponse.status(HttpStatus.FORBIDDEN).build();
        }
        return next.handle(request);
    })
    .build();
~~~

`HandlerFilterFunction` nhận `ServerRequest` và handler tiếp theo; nó có thể sửa request, short-circuit bằng response hoặc quan sát response. `before`, `after`, `filter` trên builder là cách composition filter với route function. Phạm vi của nó phụ thuộc vị trí gắn vào builder/nested router.

Annotated controller có thể dùng `@ControllerAdvice`, `HandlerInterceptor` theo mapping, method security và `WebFilter`/Spring Security. Dùng Spring Security ở WebFilter chain cho chính sách bảo mật dùng chung; đừng biến một route filter thành nơi xử lý bảo mật toàn ứng dụng.

### 11.3. Principal và security context

Cả hai mô hình có thể lấy principal/security context qua cơ chế reactive của Spring Security. Annotated controller có thể nhận `Principal`/`Authentication` trong method parameter; functional handler có thể đọc `request.principal()` hoặc context tương ứng. Security filter chain áp dụng bên ngoài endpoint model nên cùng một policy có thể bảo vệ cả hai.

## 12. Streaming và backpressure

Cả hai mô hình đều trả Publisher và hỗ trợ body stream.

Controller:

~~~java
@GetMapping(value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<Item>> events() {
    return service.events().map(item ->
        ServerSentEvent.<Item>builder()
            .id(item.id())
            .event("item")
            .data(item)
            .build());
}
~~~

Functional:

~~~java
Mono<ServerResponse> events(ServerRequest request) {
    Flux<ServerSentEvent<Item>> body = service.events().map(item ->
        ServerSentEvent.<Item>builder()
            .id(item.id())
            .event("item")
            .data(item)
            .build());

    return ServerResponse.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(body, ServerSentEvent.class);
}
~~~

Fragment functional minh họa truyền Publisher vào `ServerResponse.body`; với generic body phức tạp, dùng `ParameterizedTypeReference`/`BodyInserter` nếu codec không suy ra kiểu phần tử từ raw class. Cả hai dùng cùng codecs, network backpressure, cancellation và resource lifecycle.

**Các điểm giống nhau:**
- `Flux<T>`/Publisher có thể phát nhiều phần tử; body được ghi theo tiến trình.
- Client chậm ảnh hưởng demand/flow control và có thể làm buffer tăng.
- Client disconnect có thể cancel subscription.
- Lỗi sau khi response đã commit không thể đổi status và thay toàn bộ body.
- `collectList()` gom dữ liệu vào memory và thay semantics streaming.
- `text/event-stream`, NDJSON và JSON có framing/flush behavior khác nhau.

Khác biệt chính là cách code tạo body: annotated controller trả Publisher trực tiếp hoặc lồng trong ResponseEntity; functional handler truyền Publisher vào `ServerResponse.body(...)`.

## 13. Composition và tổ chức module

Annotated controller thường tổ chức theo resource/bounded context:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    // Các method GET/POST/DELETE của resource Order.
}
~~~

Functional endpoint thường tách route declaration và handler:

~~~java
@Configuration(proxyBeanMethods = false)
class OrderRoutes {
    @Bean
    RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
        return RouterFunctions.route()
            .path("/api/orders", b -> b
                .GET("/{id}", handler::get)
                .POST(handler::create)
                .DELETE("/{id}", handler::delete))
            .build();
    }
}
~~~

Functional composition cho phép ghép router bằng `and`, `andRoute`, `nest`, và gắn filter trước/sau theo phạm vi router. Annotated controller mạnh ở method signature, argument resolver, mapping metadata, validation và advice có sẵn.

Không có quy tắc functional luôn dễ test hơn hoặc annotated luôn dễ đọc hơn. Độ phức tạp request, số lượng route, kỹ năng team và cách chia module mới quyết định.


## 14. Java 17+ chạy được: cùng service, hai endpoint implementation

Project này chạy cả annotated và functional endpoint trong một Spring Boot WebFlux application. Hai nhóm route dùng chung service và trả cùng status/body semantics. Prefix khác nhau để hai implementation cùng tồn tại trong một server.

### 14.1. Cấu trúc dự án

~~~text
webflux-endpoint-comparison/
├── pom.xml
├── src/main/java/com/example/compare/ComparisonApplication.java
├── src/main/java/com/example/compare/Item.java
├── src/main/java/com/example/compare/CreateItemRequest.java
├── src/main/java/com/example/compare/ItemService.java
├── src/main/java/com/example/compare/ApiProblems.java
├── src/main/java/com/example/compare/AnnotatedItemController.java
├── src/main/java/com/example/compare/ApiExceptionHandler.java
├── src/main/java/com/example/compare/FunctionalItemHandler.java
├── src/main/java/com/example/compare/FunctionalItemRoutes.java
└── src/test/java/com/example/compare/EndpointContractTest.java
~~~

### 14.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-endpoint-comparison</artifactId>
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

### 14.3. ComparisonApplication.java

~~~java
package com.example.compare;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ComparisonApplication {
    public static void main(String[] args) {
        SpringApplication.run(ComparisonApplication.class, args);
    }
}
~~~

### 14.4. Item.java và CreateItemRequest.java

~~~java
package com.example.compare;

public record Item(String id, String name) {}
~~~

~~~java
package com.example.compare;

public record CreateItemRequest(String name) {}
~~~

### 14.5. ItemService.java — business logic dùng chung

~~~java
package com.example.compare;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ItemService {
    private final ConcurrentMap<String, Item> items =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(100);

    public ItemService() {
        items.put("42", new Item("42", "Seed item"));
        items.put("43", new Item("43", "Second seed"));
        items.put("delete-annotated",
            new Item("delete-annotated", "Delete annotated"));
        items.put("delete-functional",
            new Item("delete-functional", "Delete functional"));
    }

    public Mono<Item> findById(String id) {
        return Mono.justOrEmpty(items.get(id));
    }

    public Mono<Item> create(CreateItemRequest request) {
        return Mono.defer(() -> {
            String name = request == null ? null : request.name();
            if (name == null || name.isBlank()) {
                return Mono.error(
                    new IllegalArgumentException("name must not be blank"));
            }

            String id = Long.toString(sequence.incrementAndGet());
            Item item = new Item(id, name.trim());
            items.put(id, item);
            return Mono.just(item);
        });
    }

    public Mono<Boolean> deleteById(String id) {
        return Mono.fromSupplier(() -> items.remove(id) != null);
    }
}
~~~

`ConcurrentHashMap` và `AtomicLong` làm ví dụ an toàn hơn khi test/request chạy đồng thời. `Mono.defer` trì hoãn validation và ghi dữ liệu tới subscription. Đây là in-memory demo, không phải persistence bền vững; restart ứng dụng sẽ khởi tạo lại seed item.

### 14.6. ApiProblems.java — factory lỗi dùng chung

~~~java
package com.example.compare;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;

final class ApiProblems {
    private ApiProblems() {}

    static ProblemDetail invalidName(IllegalArgumentException error) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, error.getMessage());
        problem.setTitle("Invalid item");
        problem.setProperty("code", "ITEM_NAME_INVALID");
        return problem;
    }
}
~~~

### 14.7. AnnotatedItemController.java

~~~java
package com.example.compare;

import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/annotated/items")
public class AnnotatedItemController {
    private final ItemService service;

    public AnnotatedItemController(ItemService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Item>> get(@PathVariable String id) {
        return service.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().<Item>build());
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Item>> create(
            @RequestBody Mono<CreateItemRequest> body) {
        return body.flatMap(service::create)
            .map(item -> ResponseEntity
                .created(URI.create("/api/annotated/items/" + item.id()))
                .body(item));
    }

    @DeleteMapping("/{id}")
    public Mono<ResponseEntity<Void>> delete(@PathVariable String id) {
        return service.deleteById(id).map(deleted -> {
            if (deleted) {
                return ResponseEntity.noContent().<Void>build();
            }
            return ResponseEntity.notFound().<Void>build();
        });
    }
}
~~~

Controller method bind request, gọi service và biểu diễn response bằng `ResponseEntity`. GET dùng `Mono<ResponseEntity<Item>>` vì status 200/404 phụ thuộc kết quả async. POST trả 201 cùng Location. DELETE trả 204 nếu xóa được, nếu không trả 404.

### 14.8. ApiExceptionHandler.java

~~~java
package com.example.compare;

import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail invalidName(IllegalArgumentException error) {
        return ApiProblems.invalidName(error);
    }
}
~~~

Advice chuyển lỗi validation từ service thành ProblemDetail 400 cho annotated controller. Functional route dùng cùng factory nhưng có filter riêng.

### 14.9. FunctionalItemHandler.java

~~~java
package com.example.compare;

import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@Component
public class FunctionalItemHandler {
    private final ItemService service;

    public FunctionalItemHandler(ItemService service) {
        this.service = service;
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        return service.findById(request.pathVariable("id"))
            .flatMap(item -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(item))
            .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateItemRequest.class)
            .flatMap(service::create)
            .flatMap(item -> ServerResponse
                .created(URI.create(
                    "/api/functional/items/" + item.id()))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(item));
    }

    public Mono<ServerResponse> delete(ServerRequest request) {
        return service.deleteById(request.pathVariable("id"))
            .flatMap(deleted -> deleted
                ? ServerResponse.noContent().build()
                : ServerResponse.notFound().build());
    }
}
~~~

Functional handler tự đọc `ServerRequest`, decode body, lấy path variable và xây dựng `ServerResponse`. Business rule vẫn nằm trong `ItemService`, không bị nhân đôi.

### 14.10. FunctionalItemRoutes.java

~~~java
package com.example.compare;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FunctionalItemRoutes {

    @Bean
    RouterFunction<ServerResponse> functionalItemRoutes(
            FunctionalItemHandler handler) {

        return RouterFunctions.route()
            .GET("/api/functional/items/{id}", handler::get)
            .POST("/api/functional/items",
                RequestPredicates.contentType(MediaType.APPLICATION_JSON),
                handler::create)
            .DELETE("/api/functional/items/{id}", handler::delete)
            .filter((request, next) -> next.handle(request)
                .onErrorResume(IllegalArgumentException.class, error ->
                    ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                        .bodyValue(ApiProblems.invalidName(error))))
            .build();
    }
}
~~~

`RequestPredicates.contentType` giữ điều kiện Content-Type tương ứng với `consumes` của annotated route. `HandlerFilterFunction` bắt lỗi `IllegalArgumentException` từ handler/service và trả cùng ProblemDetail. Filter chỉ gắn với router này.

## 15. Kiểm thử hợp đồng HTTP cho cả hai

Test đi qua server thật để kiểm tra route mapping, body codec, status và headers. Chỉ gọi trực tiếp controller method/handler function sẽ bỏ qua một phần pipeline mà client thực sự sử dụng.

### 15.1. EndpointContractTest.java

~~~java
package com.example.compare;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class EndpointContractTest {
    private static final HttpClient CLIENT = HttpClient.newHttpClient();

    @Value("${local.server.port}")
    int port;

    private HttpResponse<String> send(
            String method, String path, String body) throws Exception {

        HttpRequest.Builder builder = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + path))
            .header("Accept",
                "application/json, application/problem+json");

        HttpRequest.BodyPublisher publisher = body == null
            ? HttpRequest.BodyPublishers.noBody()
            : HttpRequest.BodyPublishers.ofString(body);

        if (body != null) {
            builder.header("Content-Type", "application/json");
        }

        return CLIENT.send(
            builder.method(method, publisher).build(),
            HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void getExistingItemHasSameContract() throws Exception {
        HttpResponse<String> annotated = send(
            "GET", "/api/annotated/items/42", null);
        HttpResponse<String> functional = send(
            "GET", "/api/functional/items/42", null);

        assertEquals(200, annotated.statusCode());
        assertEquals(annotated.statusCode(), functional.statusCode());
        assertEquals(annotated.body(), functional.body());
        assertTrue(annotated.body().contains("\"name\":\"Seed item\""));
    }

    @Test
    void missingItemReturnsSameNotFoundContract() throws Exception {
        HttpResponse<String> annotated = send(
            "GET", "/api/annotated/items/missing-xyz", null);
        HttpResponse<String> functional = send(
            "GET", "/api/functional/items/missing-xyz", null);

        assertEquals(404, annotated.statusCode());
        assertEquals(annotated.statusCode(), functional.statusCode());
        assertEquals("", annotated.body());
        assertEquals(annotated.body(), functional.body());
    }

    @Test
    void createReturnsCreatedLocationAndJsonFromBothModels()
            throws Exception {
        HttpResponse<String> annotated = send(
            "POST", "/api/annotated/items", "{\"name\":\"Keyboard\"}");
        HttpResponse<String> functional = send(
            "POST", "/api/functional/items", "{\"name\":\"Keyboard\"}");

        assertEquals(201, annotated.statusCode());
        assertEquals(annotated.statusCode(), functional.statusCode());
        assertTrue(annotated.headers()
            .firstValue("Location").orElse("")
            .startsWith("/api/annotated/items/"));
        assertTrue(functional.headers()
            .firstValue("Location").orElse("")
            .startsWith("/api/functional/items/"));
        assertTrue(annotated.body().contains("\"name\":\"Keyboard\""));
        assertTrue(functional.body().contains("\"name\":\"Keyboard\""));
        assertTrue(annotated.headers()
            .firstValue("Content-Type").orElse("")
            .startsWith("application/json"));
        assertTrue(functional.headers()
            .firstValue("Content-Type").orElse("")
            .startsWith("application/json"));
    }

    @Test
    void invalidInputReturnsEquivalentProblemDetail()
            throws Exception {
        String invalid = "{\"name\":\" \"}";
        HttpResponse<String> annotated = send(
            "POST", "/api/annotated/items", invalid);
        HttpResponse<String> functional = send(
            "POST", "/api/functional/items", invalid);

        assertEquals(400, annotated.statusCode());
        assertEquals(annotated.statusCode(), functional.statusCode());
        assertTrue(annotated.body().contains("name must not be blank"));
        assertTrue(functional.body().contains("name must not be blank"));
        assertTrue(annotated.body().contains("ITEM_NAME_INVALID"));
        assertTrue(functional.body().contains("ITEM_NAME_INVALID"));
    }

    @Test
    void deleteUsesSameNoContentAndNotFoundSemantics()
            throws Exception {
        HttpResponse<String> annotatedDelete = send(
            "DELETE", "/api/annotated/items/delete-annotated", null);
        HttpResponse<String> functionalDelete = send(
            "DELETE", "/api/functional/items/delete-functional", null);

        assertEquals(204, annotatedDelete.statusCode());
        assertEquals(204, functionalDelete.statusCode());
        assertTrue(annotatedDelete.body().isEmpty());
        assertTrue(functionalDelete.body().isEmpty());

        HttpResponse<String> annotatedAgain = send(
            "DELETE", "/api/annotated/items/delete-annotated", null);
        HttpResponse<String> functionalAgain = send(
            "DELETE", "/api/functional/items/delete-functional", null);

        assertEquals(404, annotatedAgain.statusCode());
        assertEquals(404, functionalAgain.statusCode());
    }
}
~~~

Test dùng `HttpClient` có sẵn trong JDK 17; `RANDOM_PORT` khởi chạy embedded server. Hai seed ID riêng cho DELETE giúp các test không phụ thuộc thứ tự chạy.

### 15.2. Chạy ứng dụng

Yêu cầu JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Ứng dụng mặc định nghe cổng 8080. Request thử:

~~~bash
curl -i http://localhost:8080/api/annotated/items/42
curl -i http://localhost:8080/api/functional/items/42
curl -i -X POST http://localhost:8080/api/annotated/items -H "Content-Type: application/json" -d "{\"name\":\"Keyboard\"}"
curl -i -X POST http://localhost:8080/api/functional/items -H "Content-Type: application/json" -d "{\"name\":\"Keyboard\"}"
~~~

**Kết quả chính:**

| Request | Annotated | Functional |
| --- | --- | --- |
| GET item 42 | 200 + JSON | 200 + cùng JSON |
| GET id không có | 404 + body rỗng | 404 + body rỗng |
| POST name hợp lệ | 201 + Location + JSON | 201 + Location + JSON |
| POST name trống | 400 + ProblemDetail | 400 + cùng schema ProblemDetail |
| DELETE item tồn tại | 204 + body rỗng | 204 + body rỗng |
| DELETE lại item đã xóa | 404 + body rỗng | 404 + body rỗng |

Location chứa prefix riêng của implementation; đó là khác biệt có chủ đích trong demo để hai route cùng chạy trên một server.

## 16. Chọn mô hình theo tình huống

| Tình huống | Thường thuận tiện hơn | Lý do |
| --- | --- | --- |
| CRUD REST tiêu chuẩn, nhiều path/header/body binding | Annotated controller | Method signature và resolver làm phần lớn công việc. |
| Endpoint cần đọc request theo nhiều nhánh rõ ràng | Functional | `ServerRequest` và chuỗi Mono làm thứ tự xử lý tường minh. |
| Nhiều route ghép theo predicate/nested path | Functional | Router composition là API cốt lõi. |
| Dùng `@Valid`, `@ModelAttribute`, `@ExceptionHandler` nhiều | Annotated | Hỗ trợ convention và integration sẵn. |
| Một nhóm route cần before/after/filter riêng | Functional | `HandlerFilterFunction` gắn trực tiếp với router. |
| Team quen controller và annotation Spring | Annotated | Ít thay đổi quy ước, dễ onboard. |
| Module muốn biểu diễn routing bằng composition | Functional | Route có thể ghép thành các phần độc lập. |
| Cross-cutting security/logging cho cả ứng dụng | Cả hai | Dùng WebFilter/Spring Security ngoài endpoint model. |
| Cùng service/domain phục vụ nhiều loại route | Cả hai | Chia sẻ service và kiểm thử contract chung. |

Không cần chọn một mô hình cho toàn bộ ứng dụng. Một codebase có thể dùng annotated controllers cho CRUD thông thường và functional router cho module stream hoặc gateway cần composition rõ ràng. Hãy thống nhất quy ước trong từng module để tránh hai cách xử lý lỗi/validation khác nhau ngoài ý muốn.

## 17. Sai lầm khi chuyển đổi hoặc triển khai song song

| Sai lầm | Hậu quả | Cách kiểm tra/sửa |
| --- | --- | --- |
| Chỉ so sánh JSON body, bỏ qua status/headers | Hai endpoint tưởng giống nhưng contract khác | Test status, Location, Content-Type và error headers. |
| Validation khác nhau | Input giống nhau cho kết quả khác | Đưa domain validation vào service/validator dùng chung. |
| Nghĩ `@ControllerAdvice` bắt lỗi functional handler | Functional route có thể trả lỗi khác | Functional filter hoặc WebExceptionHandler chung. |
| Nghĩ functional route luôn chọn route cụ thể nhất | Route tổng quát khai báo trước bắt request | Kiểm tra thứ tự composition và predicate. |
| Duplicate path/method ở hai mô hình | Route shadowing hoặc dispatch khó đoán | Dùng prefix rõ trong giai đoạn coexist hoặc cấu hình order có chủ đích. |
| Dùng WebFilter thay route-specific filter | Logic endpoint áp dụng quá rộng | HandlerFilterFunction cho router; WebFilter cho cross-cutting. |
| Đọc request body nhiều lần | Body đã tiêu thụ, handler sau không đọc lại được | Decode một lần hoặc cache/decorate có chủ đích. |
| Tự ghi response rồi tiếp tục ghi body | Response commit hai lần/lỗi | Chọn một response owner. |
| Gọi `block()`/`subscribe()` trong handler | Mất reactive lifecycle, block event-loop | Compose Publisher và trả kết quả cho framework. |
| Chỉ test handler trực tiếp | Bỏ qua mapping, codec và HTTP headers | Thêm HTTP integration tests qua RANDOM_PORT. |
| Bỏ qua cancellation trong streaming | Listener/connection có thể leak | Gắn cleanup vào Publisher và test client disconnect. |
| Functional route không có content-type predicate | Nhận request ngoài contract | Dùng `contentType`/`accept` predicate hoặc kiểm tra trong handler. |
| Dùng prefix khác nhau rồi so Location nguyên văn | Test báo khác giả tạo | Chuẩn hóa prefix hoặc so các thành phần contract riêng. |

## 18. Parity matrix trước khi chuyển endpoint

Khi chuyển một controller sang functional route hoặc ngược lại, hãy ghi parity theo từng endpoint:

1. **Request matching:** method, path, query, header, content type, Accept, version.
2. **Input binding:** path variable, query parameter, body type, cookie, principal, validation.
3. **Success:** status, Location, cache headers, content type, JSON schema, empty body.
4. **Failure:** 400/401/403/404/409/415/406/5xx, ProblemDetail, correlation ID.
5. **Reactive behavior:** Mono/Flux cardinality, backpressure, timeout, cancellation, cleanup.
6. **Security:** authentication, authorization, CSRF/CORS nếu áp dụng, method security.
7. **Observability:** logs, metrics, tracing, request ID và latency.
8. **Compatibility:** serialization naming, date/time format, enum, null handling và versioned response.

Kiểm tra cả empty result, body lỗi decode, validation fail, route không match, media type sai, client disconnect và response stream lỗi giữa chừng. Đây là nơi hai implementation dễ lệch contract dù happy path có body giống nhau.

## 19. Checklist production

- [ ] Hai implementation dùng chung domain service và quy tắc nghiệp vụ.
- [ ] Method/path/predicate khớp HTTP contract.
- [ ] Functional route order và nested predicates được kiểm tra.
- [ ] Annotated mapping không mơ hồ và không bị route khác shadow.
- [ ] Body được decode đúng bằng message reader/codec.
- [ ] Validation có semantics giống nhau.
- [ ] Status, headers, Location, content type và body schema giống nhau.
- [ ] Error mapping có cùng ProblemDetail/status; hiểu phạm vi @ControllerAdvice và functional filter.
- [ ] Security/cross-cutting dùng đúng tầng WebFilter/Spring Security.
- [ ] Streaming giữ backpressure, timeout, cancellation và cleanup.
- [ ] Không block hoặc tự subscribe trong request path.
- [ ] Integration test chạy qua HTTP server cho cả hai kiểu endpoint.
- [ ] Logging, metrics, tracing và request ID không phụ thuộc mô hình handler.
- [ ] Có thể rollout từng route và so sánh contract trước khi xóa implementation cũ.

## 20. Bài tập thực hành

**Bài 1 – GET parity.** Viết GET `/items/{id}` bằng hai mô hình. Kiểm tra 200 khi tồn tại và 404 khi không tồn tại; so status và JSON body.

**Bài 2 – POST parity.** Viết POST nhận JSON, validate name, trả 201 và Location. Gửi name rỗng; đảm bảo hai bên trả cùng ProblemDetail.

**Bài 3 – DELETE parity.** Viết DELETE trả 204 khi xóa được, 404 khi không có. Kiểm tra body rỗng và gọi lần hai.

**Bài 4 – Route specificity.** Khai báo route `/items/search` và `/items/{id}`. Đặt route tổng quát trước rồi đảo thứ tự; quan sát cách RouterFunction chọn handler. So với annotated mapping.

**Bài 5 – Validation.** Annotated dùng `@Valid`; functional dùng Validator hoặc domain service. Đảm bảo cùng constraint và error code.

**Bài 6 – Filter scope.** Thêm WebFilter ghi request ID cho cả hai route. Thêm HandlerFilterFunction chỉ cho functional route; xác nhận scope khác nhau.

**Bài 7 – Streaming.** Trả cùng Flux SSE qua controller và ServerResponse. Ngắt client, xác nhận cleanup upstream và so sánh framing.

**Bài 8 – Chuyển đổi endpoint thật.** Chọn một endpoint hiện có, ghi parity matrix, implement mô hình thứ hai dưới path thử nghiệm và chạy cùng bộ HTTP contract test trước khi chuyển traffic.

## 21. Tài liệu tham khảo chính thức

1. Spring Framework – Functional Endpoints (WebFlux.fn): https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
2. Spring Framework – Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
3. Spring Framework – WebFlux overview và hai programming models: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
4. Spring Framework – DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
5. Spring Framework – WebFlux Config: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
6. Spring Framework – Error Responses / ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
7. Spring Framework – Reactive Libraries: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
8. Spring Security – Reactive WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html

**Tự đánh giá cuối:** Nếu client gửi cùng một GET hoặc POST đến hai implementation, những gì phải giống nhau để được xem là cùng HTTP contract? Vì sao `@ControllerAdvice` không thay thế mọi functional route filter? Khi nào route composition của WebFlux.fn giúp code dễ kiểm soát hơn, và khi nào annotated method signature tiết kiệm công sức hơn? Hãy trả lời bằng status/header/body/error tests, không chỉ dựa vào hai method trả cùng object.

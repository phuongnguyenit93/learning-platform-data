# WebMvc.fn và khác biệt với controller dùng annotation trong Spring MVC

## 1. WebMvc.fn giải quyết bài toán gì?

Trong Spring Web MVC, cách viết endpoint phổ biến là đặt `@RestController`, `@GetMapping`, `@PostMapping` lên class/method. Spring sẽ đọc metadata annotation và quyết định handler thích hợp. **WebMvc.fn** là một **mô hình lập trình functional** thay thế: ta mô tả các quy tắc route bằng `RouterFunction`, rồi đưa request vào `HandlerFunction` để nhận `ServerResponse`.

Hai mô hình **chạy trên cùng hệ sinh thái Servlet/MVC**, không phải lựa chọn giữa thread blocking và reactive server:

- **Annotated MVC:** ánh xạ request với controller method bằng annotation và các argument/return-value resolvers.
- **WebMvc.fn:** ánh xạ request bằng các hàm predicate/router và xử lý qua interfaces `ServerRequest`/`ServerResponse`.
- **Cùng hạ tầng:** `DispatcherServlet`, Servlet container, HTTP message converters, filters, Spring IoC và phần lớn cấu hình MVC.
- **Không đồng nhất với WebFlux.fn:** các class WebFlux nằm trong `org.springframework.web.reactive.function.server` và dùng `Mono`/`Flux`; MVC dùng `org.springframework.web.servlet.function` và các body APIs theo Servlet stack.

Bài này trình bày **Spring Framework 6.1.x**, **Spring Boot 3.3.5**, **Java 17**. Mục đích là hiểu kiến trúc và chọn phong cách phù hợp, không tuyên bố functional MVC nhanh hơn controller annotation hay tự động tạo non-blocking I/O.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt `RouterFunction`, `RequestPredicate`, `HandlerFunction`, `ServerRequest` và `ServerResponse`.
2. Xây routes GET/POST có path variables, query parameters và JSON body.
3. Dùng `route()`, `path()`, `nest()`, `and(...)` và route order chính xác.
4. Chọn status, content type, body và `Location` bằng `ServerResponse`.
5. Thực hiện validation/exception handling khi không có `@Valid @RequestBody` trên tham số controller.
6. Viết functional filters bằng `before`, `after` và `filter`, biết phạm vi áp dụng.
7. So sánh cùng một API được triển khai bằng WebMvc.fn và annotated controllers.
8. Chạy ví dụ Maven hoàn chỉnh, gọi curl và test bằng MockMvc.
9. Nhận diện security, CORS, request binding, OpenAPI, khả năng bảo trì và các lỗi migration.
10. Hiểu vì sao WebMvc.fn **vẫn có thể blocking** và khác WebFlux.fn.

## 2. Nền tảng: HTTP request đi qua Spring MVC như thế nào?

Với request:

```http
GET /fn/books/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

Annotated controller có thể được khai báo:

```java
@RestController
@RequestMapping("/ann/books")
public class AnnotatedBooks {
    @GetMapping("/{id}")
    public Book get(@PathVariable long id) {
        return service.find(id);
    }
}
```

Đây là **snippet mô tả**; class `Book` và `service` chưa định nghĩa. Spring xem annotation mapping, chuyển `"42"` thành `long`, gọi method và serialize body thành JSON.

Functional MVC tương đương về mục tiêu:

```java
RouterFunction<ServerResponse> routes = route()
        .GET("/fn/books/{id}", request -> {
            long id = Long.parseLong(request.pathVariable("id"));
            Book book = service.find(id);
            return ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(book);
        })
        .build();
```

Đây cũng là **snippet**: `service` chưa định nghĩa và thiếu imports. Điểm quan trọng là route + handler nằm trong các giá trị/function Java, không phải annotation metadata.

### Đường đi của một request WebMvc.fn

```text
Client HTTP request
         |
         v
Servlet Filter chain / Spring Security
         |
         v
DispatcherServlet
         |
         v
RouterFunctionMapping
  - thử các RouterFunction
  - đánh giá RequestPredicate
  - chọn HandlerFunction đầu tiên phù hợp
         |
         v
HandlerFunctionAdapter
  - gọi handler.handle(ServerRequest)
         |
         v
ServerResponse.writeTo(...)
  - HTTP status / headers / body conversion
         |
         v
Servlet response
```

Đây là sơ đồ giản lược. WebMvc.fn dùng các MVC components tương ứng để tích hợp với `DispatcherServlet`. Với annotation, `RequestMappingHandlerMapping` và `RequestMappingHandlerAdapter` đảm nhiệm bước mapping/invocation. **Cùng DispatcherServlet không có nghĩa cùng mọi argument resolver/interceptor behavior.**

Khi đăng ký `RouterFunction<ServerResponse>` dưới dạng bean trong Spring context, MVC tự phát hiện router và lắp vào hạ tầng mapping. Với Spring Boot web starter, ứng dụng MVC cơ bản **không cần thêm WebFlux dependency** và thường không cần `@EnableWebMvc`. Việc tự đặt `@EnableWebMvc` trong Boot có thể thay đổi các auto-configurations nên không thêm tùy tiện.

## 3. Năm thành phần cốt lõi của WebMvc.fn

### 3.1. RequestPredicate — một quy tắc match

`org.springframework.web.servlet.function.RequestPredicate` quyết định một request có phù hợp hay không. `RequestPredicates` cung cấp predicates theo HTTP method, path, headers, Accept, Content-Type.

Ví dụ:

```java
RequestPredicate rule = GET("/fn/books/{id}")
        .and(accept(MediaType.APPLICATION_JSON));
```

Đây là snippet với static imports `GET` và `accept` từ `RequestPredicates`. Nếu request thỏa cả GET/path và Accept, rule có thể chọn handler. `and`, `or` và `negate` cho phép kết hợp predicates.

**Chú ý:** Predicate `accept(APPLICATION_JSON)` kiểm tra header `Accept`, tức kiểu client muốn **nhận**. Predicate `contentType(APPLICATION_JSON)` kiểm tra `Content-Type`, tức kiểu body client **gửi**. Không tráo hai headers.

### 3.2. HandlerFunction — công việc xử lý request

`HandlerFunction<T extends ServerResponse>` là functional interface. Về ý nghĩa:

```java
ServerResponse handle(ServerRequest request) throws Exception;
```

Chữ ký trên chỉ để nhớ khái niệm; exception declaration cụ thể phụ thuộc API, hãy xem Javadoc 6.1. Handler có thể là lambda hoặc method reference:

```java
HandlerFunction<ServerResponse> hello =
        request -> ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body("Hello MVC");
```

Một controller annotation method có nhiều tham số Spring tự resolve; functional handler thường nhận **một `ServerRequest`** rồi chủ động đọc path/query/header/body.

### 3.3. ServerRequest — đọc dữ liệu đầu vào

`org.springframework.web.servlet.function.ServerRequest` cung cấp:

| API | Tác dụng |
| --- | --- |
| `request.pathVariable("id")` | Giá trị path placeholder |
| `request.pathVariables()` | Map các path variables |
| `request.param("q")` | `Optional<String>` của query/form param |
| `request.params()` | `MultiValueMap<String,String>` các parameters |
| `request.headers()` | `ServerRequest.Headers`, gồm Accept/Content-Type/custom headers |
| `request.body(MyDto.class)` | Giải mã body bằng `HttpMessageConverter`, có thể throw |
| `request.body(new ParameterizedTypeReference<List<MyDto>>() {})` | Đọc generic collection |
| `request.servletRequest()` | Truy cập Servlet request khi thực sự cần |
| `request.principal()` | Access authenticated principal nếu có |

Ví dụ:

```java
long id = Long.parseLong(request.pathVariable("id"));
String q = request.param("q").orElse("");
CreateBookRequest dto = request.body(CreateBookRequest.class);
```

Đây là snippet cần `request` thuộc một functional handler. Trên annotated controller, các phần này có thể là `@PathVariable long id`, `@RequestParam(defaultValue="") String q` và `@RequestBody CreateBookRequest dto`.

Functional không tự có **magic** với việc parse `long`: `pathVariable()` trả String; bạn cần parse và xử lý `NumberFormatException` hay chọn policy lỗi rõ ràng. Với body JSON, `request.body(...)` dùng converter đã đăng ký và có thể báo lỗi khi JSON sai, thiếu body hoặc media type không được hỗ trợ.

### 3.4. ServerResponse — khai báo HTTP response

`org.springframework.web.servlet.function.ServerResponse` cung cấp builder-style APIs:

```java
ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(book);

ServerResponse.created(URI.create("/fn/books/42"))
        .contentType(MediaType.APPLICATION_JSON)
        .body(book);

ServerResponse.noContent().build();

ServerResponse.status(HttpStatus.BAD_REQUEST)
        .contentType(MediaType.APPLICATION_JSON)
        .body(new ApiError("invalid_request"));
```

Đây là **snippets** có biến `book`/class `ApiError` từ ứng dụng giả định. Không dùng `ServerResponse.bodyValue(...)` của WebFlux.fn trong MVC: API Servlet `ServerResponse.BodyBuilder` dùng `body(...)` cho object thông thường.

Body converter/serialization của Spring được dùng khi ghi response. Dùng `ServerResponse.created(URI)` tạo HTTP 201 và header `Location` tương ứng, chứ không cần tự viết `status=201` trong JSON body.

### 3.5. RouterFunction — từ request tới handler

`RouterFunction<T>` khi match request sẽ trả optional handler function. Thực tế thường dùng builder:

```java
RouterFunction<ServerResponse> api = RouterFunctions.route()
        .GET("/fn/hello", request ->
                ServerResponse.ok().body("Hello"))
        .GET("/fn/status", request ->
                ServerResponse.ok().body("ready"))
        .build();
```

Builder có thể tạo một router từ nhiều rules, thêm nested routes và filters. **Order của functional routes là một phần của behavior** — route đầu tiên match có thể thắng.

## 4. Khác biệt cốt lõi: route order

Trong annotated MVC, `RequestMappingHandlerMapping` có logic so sánh độ cụ thể của mapping. Ví dụ `/books/latest` thường được chọn thay `/books/{id}` nhờ độ cụ thể, dù hai methods được viết trong file theo thứ tự nào.

Trong WebMvc.fn, **routes được thử theo thứ tự**. Vì vậy:

```java
// CẦN CẨN THẬN: /books/{id} đặt trước /books/latest
RouterFunction<ServerResponse> wrong = route()
        .GET("/fn/books/{id}", handler::getBook)
        .GET("/fn/books/latest", handler::latest)
        .build();
```

Request `GET /fn/books/latest` có thể match placeholder `{id}`, đưa string `"latest"` tới handler lấy ID. Kết quả có thể là lỗi parsing thay vì endpoint latest.

Đặt specific route lên trước:

```java
RouterFunction<ServerResponse> correct = route()
        .GET("/fn/books/latest", handler::latest)
        .GET("/fn/books/{id}", handler::getBook)
        .build();
```

Hai ví dụ là snippets với `handler` giả định. **Đừng chỉ sắp xếp theo alphabet**. Cần có test để bảo vệ thứ tự những route có thể trùng match.

Khi có **nhiều RouterFunction beans**, Spring MVC phát hiện/sắp xếp/chaining theo infrastructure. Thứ tự có thể chịu ảnh hưởng bean ordering/configuration. Vì vậy với các routes có xung đột, đừng mặc định thứ tự file hay tên bean; ưu tiên group rõ ràng, dùng `@Order`/ordering policy phù hợp và kiểm thử route collisions.

Khi dùng cả annotations và functional endpoints ở chung một DispatcherServlet, mỗi phong cách có mapping component riêng; không suy luận độ ưu tiên cross-style chỉ từ thứ tự khai báo Java. Kiểm tra behavior của phiên bản Spring/framework config nếu hai phong cách cùng định nghĩa chính xác một URL + method.

## 5. Nested routes và composition

### 5.1. Nhóm bằng path()

Nếu tất cả endpoint dùng chung prefix `/fn/books`:

```java
RouterFunction<ServerResponse> routes = route()
        .path("/fn/books", books -> books
                .GET("/latest", handler::latest)
                .GET("/{id}", handler::getBook)
                .GET(handler::listBooks)
                .POST(handler::createBook))
        .build();
```

Đây là snippet với handler class giả định. `.path("/fn/books", builder -> ...)` không chỉ là nối chuỗi: nó tạo nested route group và áp prefix/predicate của nhóm. Method `GET(handler::listBooks)` trong nested builder match root route của group. Ưu tiên đường cụ thể trước đường biến.

### 5.2. Nest theo predicate

Ví dụ một nhóm GET routes cùng muốn JSON:

```java
RouterFunction<ServerResponse> routes = route()
        .path("/fn/books", books -> books
                .nest(accept(MediaType.APPLICATION_JSON), json -> json
                        .GET("/latest", handler::latest)
                        .GET("/{id}", handler::getBook)
                        .GET(handler::listBooks))
                .POST(handler::createBook))
        .build();
```

Đây là snippet. `accept(APPLICATION_JSON)` giới hạn **nhóm GET**, không giới hạn POST ở bên ngoài `nest`. Nếu client gửi `Accept: text/html`, route GET có thể không match, tạo behavior khác hẳn việc handler chạy rồi serializer chọn format; vì vậy response **404/406** cho unmatched predicates không nên được giả định giống controller annotation `produces`. Test cụ thể error contract.

### 5.3. Composition bằng and()/andRoute()

Khi có hai route groups độc lập:

```java
RouterFunction<ServerResponse> all =
        catalogRoutes.and(searchRoutes);
```

Hoặc builder `route().add(catalogRoutes).add(searchRoutes).build()`. Đó là việc **nối hành vi routing**, không phải copy annotations. Thứ tự thường quan trọng nếu rules có thể cùng match. Nên chia theo domain/module để có cấu trúc kiểm thử được.

### 5.4. RouterFunction là Spring bean, không phải controller annotation

Một bean:

```java
@Configuration
class Routes {
    @Bean
    RouterFunction<ServerResponse> router(BookHandler handler) {
        return route()
                .GET("/fn/books", handler::listBooks)
                .build();
    }
}
```

Đây là snippet với `BookHandler`, `route()` static import. Spring MVC tự nhận diện bean router. Không cần gắn `@RestController` lên handler function; handler là một Spring bean/service thuần hoặc lambda, còn Spring IoC vẫn injection như bình thường.

## 6. Filters của WebMvc.fn: before, after và filter

Functional routes có khả năng gắn filters ở tầng router. Cần phân biệt chúng với **Servlet Filter** và **Spring Security filter chain**.

### 6.1. before: biến đổi request được truyền cho handler

```java
RouterFunction<ServerResponse> router = route()
        .GET("/fn/hello", handler::hello)
        .before(request -> ServerRequest.from(request)
                .header("X-Internal-Marker", "functional")
                .build())
        .build();
```

Đây là snippet với `handler` đã tồn tại. `before` có thể tạo một `ServerRequest` wrapper mới để route handlers nhìn thấy request metadata đã được bổ sung. Không lấy nó làm giải pháp xác thực: client vẫn có thể tự gửi headers; auth phải dựa trên Spring Security/credentials và quy tắc trust.

### 6.2. after: quan sát hoặc thay đổi response

`after` nhận `(request, response)` rồi trả một `ServerResponse`. Ví dụ:

```java
RouterFunction<ServerResponse> router = route()
        .GET("/fn/hello", handler::hello)
        .after((request, response) -> {
            auditService.record(
                    request.path(), response.statusCode());
            return response;
        })
        .build();
```

Đây là snippet với `auditService` giả định. Nếu cần gắn header vào response, có thể dùng response builder/copy API theo Javadoc và kiểm thử sự tương thích với body/commit status. Do response contract bất biến, đừng thử sửa properties trực tiếp theo cách mutable annotated `HttpServletResponse` nếu code không quản lý lifecycle.

### 6.3. filter: bao quanh handler và có thể short-circuit

`HandlerFilterFunction` nhận request và `next` handler. Một filter có thể gọi `next.handle(request)` hoặc chặn:

```java
RouterFunction<ServerResponse> router = route()
        .GET("/fn/hello", handler::hello)
        .filter((request, next) -> {
            if ("true".equals(
                    request.headers().firstHeader("X-Demo-Block"))) {
                return ServerResponse.status(HttpStatus.FORBIDDEN)
                        .body("blocked");
            }
            return next.handle(request);
        })
        .build();
```

Đây là snippet chỉ dùng **header giả lập để học short-circuit**, tuyệt đối **không sử dụng như kiểm tra authorization thực tế**. Một client có thể gửi hoặc không gửi header đó theo ý họ. Trong demo đầy đủ, filter này sẽ giúp test chứng minh functional filter chỉ áp dụng cho functional route group.

### 6.4. Nested filter scope

Filters đặt ở root builder ảnh hưởng các routes do builder ấy tạo; filters ở nested builder chỉ áp dụng cho nested routes, không tự lan ra các route sibling/parent bên ngoài phạm vi. Điều này khác Servlet Filter theo URL mappings.

**Không nhầm ba tầng:**

| Tầng | Điểm can thiệp | Dùng khi nào |
| --- | --- | --- |
| Servlet `Filter` | Trước DispatcherServlet; có thể áp dụng mọi endpoint, static routes và annotations theo mapping | Security filter chain, correlation ID, servlet-level concerns |
| `HandlerInterceptor` / `WebMvcConfigurer` | MVC handler lifecycle, theo mapping và execution flow | MVC cross-cutting behavior; kiểm tra tương thích functional dispatch |
| WebMvc.fn `HandlerFilterFunction` | Bao quanh functional `HandlerFunction` đã được route match | Per-router logging, response adaptations, routing policies |

Đặc biệt **Spring Security** nên được cấu hình tại security filter chain/path policies; đừng thay bằng WebMvc.fn header-check filter hoặc tin filter thứ tự tùy ý. Các exceptions từ functional handlers cũng cần được xử lý phù hợp trong MVC/global/error path — không suy luận rằng mọi `@ControllerAdvice`/`@ExceptionHandler` trong annotated controllers sẽ xử lý chính xác giống nhau cho functional endpoint; có thể dùng router filters hoặc error handling được kiểm thử riêng.

## 7. JSON body, validation và exception handling

### 7.1. Với annotated controller

```java
@PostMapping("/ann/books")
public ResponseEntity<Book> create(
        @Valid @RequestBody NewBook input) {
    Book book = service.create(input);
    return ResponseEntity
            .created(URI.create("/ann/books/" + book.id()))
            .body(book);
}
```

Đây là snippet với `NewBook`/`service` chưa định nghĩa. Spring MVC tự resolve `@RequestBody` bằng `HttpMessageConverter`, `@Valid` kích hoạt Bean Validation khi có validator, và nếu không có `BindingResult` để nhận lỗi thì có thể phát sinh `MethodArgumentNotValidException`. Pipeline annotated tự tích hợp khá nhiều annotation metadata.

### 7.2. Với WebMvc.fn

```java
public ServerResponse createBook(ServerRequest request)
        throws Exception {
    NewBook input = request.body(NewBook.class);

    var errors = validator.validate(input);
    if (!errors.isEmpty()) {
        return ServerResponse.badRequest()
                .body(new ApiError("invalid_title"));
    }
    Book book = service.create(input);
    return ServerResponse.created(
            URI.create("/fn/books/" + book.id()))
            .body(book);
}
```

Đây là snippet với `validator`/`service` được inject và các record classes ở mục 10. `ServerRequest.body(NewBook.class)` dùng converter để đọc JSON; annotation `@NotBlank` trên DTO vẫn có thể được validator kiểm tra, nhưng **phải chủ động gọi `validator.validate(input)`** trong functional handler hoặc thiết kế validation binder/filter phù hợp. Đừng kỳ vọng khai báo `@Valid` trên một tham số method `HandlerFunction.handle(ServerRequest)` tự nhiên hoạt động như method argument resolution của annotated controller.

### 7.3. Lỗi JSON malformed không giống lỗi validation

- **Malformed JSON:** converter không deserialize được, có thể ném exception trước `validator.validate`.
- **Invalid DTO field:** parse JSON xong rồi Bean Validation phát hiện constraint.
- **Missing path ID/non-numeric ID:** functional handler parse `request.pathVariable`; cần quy định 400 hoặc 404.
- **Unsupported media type:** `contentType` predicate có thể làm route không match, vì vậy **không mặc định** response sẽ giống annotated `@PostMapping(consumes=...)`.
- **Unauthorized:** auth/filter chain cần kiểm tra quyền, không chỉ validation/serialization.

Nếu API bắt buộc mọi lỗi trả RFC 9457 `ProblemDetail` hoặc JSON error schema nhất quán, hãy xây các handlers/advice/filters đủ coverage và test từng path; không hứa rằng chuyển đổi từ annotated sang functional giữ nguyên tất cả exception mappings.

## 8. WebMvc.fn có đồng nghĩa non-blocking hoặc reactive không?

**Không.** Lớp Servlet `ServerRequest` có method `body(Class)` đọc body thông qua MVC converters; handler có thể gọi JDBC/JPA hoặc REST client đồng bộ. Chỉ vì cú pháp route là lambda không làm I/O trở thành asynchronous:

```java
HandlerFunction<ServerResponse> slow = request -> {
    Book book = blockingRepository.findById(42);
    return ServerResponse.ok().body(book);
};
```

Đây là snippet minh họa; `blockingRepository` chưa định nghĩa. Trong lúc `findById` chờ, Servlet thread có thể bị giữ như controller đồng bộ thông thường. Functional **WebMvc.fn** vẫn chạy trên Servlet MVC.

So với **WebFlux.fn**:

| Đặc điểm | WebMvc.fn | WebFlux.fn |
| --- | --- | --- |
| Package | `org.springframework.web.servlet.function` | `org.springframework.web.reactive.function.server` |
| Request | Servlet `ServerRequest` | Reactive `ServerRequest` |
| Response | Servlet `ServerResponse` (object) | Reactive `Mono<ServerResponse>` |
| Body object | `ServerResponse.ok().body(book)` | `ServerResponse.ok().bodyValue(book)` / publishers |
| Routing | Servlet `RouterFunction` | Reactive `RouterFunction` |
| Runtime | DispatcherServlet / Servlet stack | DispatcherHandler / reactive stack |
| I/O behavior | Synchronous/blocking code có thể chạy trực tiếp | Thiết kế reactive, nhưng dependency blocking vẫn có thể chặn event loop |
| Testing | MockMvc | WebTestClient và reactive testing tools |
| Nhu cầu | Functional style với Spring MVC hiện có | End-to-end reactive pipelines nếu I/O hỗ trợ |

**Đừng import nhầm classes theo tên ngắn giống nhau.** Cùng có `ServerRequest`, `ServerResponse` và `RouterFunction` nhưng package/subtype/phương thức khác. Với Spring Boot app đã có `spring-boot-starter-web`, dùng WebMvc.fn mà không thêm `spring-boot-starter-webflux` chỉ để lấy router APIs.

## 9. Khi nào chọn functional route, khi nào giữ annotated controller?

| Tiêu chí | Annotated controllers | WebMvc.fn |
| --- | --- | --- |
| Cách routing | `@GetMapping`, `@PostMapping` trên methods | `route().GET(...).POST(...)` DSL |
| Binding của path/query | `@PathVariable` / `@RequestParam` auto-resolve | `request.pathVariable` / `request.param` chủ động |
| JSON request | `@RequestBody Dto` | `request.body(Dto.class)` |
| Bean Validation | `@Valid` và MVC argument resolution | Validator/binding explicit theo thiết kế |
| HTTP response | `ResponseEntity`, DTO, view name | `ServerResponse` builder |
| Path grouping | `@RequestMapping` ở type-level | `path()`/`nest()` |
| Route precedence | Mapping specificity comparison | **Thứ tự khai báo routes** |
| Cross-cutting | Servlet filters, interceptors, advice | Servlet filters + router before/after/filter; error policy explicit |
| API docs generation | Nhiều OpenAPI tools hiểu annotation tốt hơn | Có thể cần tooling/integration riêng, tùy version |
| Kotlin DSL / Java lambdas | Có thể dùng annotations trên Kotlin/Java classes | Functional composition thuận tiện, Kotlin router DSL |
| Cùng project | Có | Có, test overlapping paths |
| Non-blocking | Không tự động | **Không tự động** |

### Những lúc WebMvc.fn hữu ích

- Xây một module API nhỏ, ít handler, muốn route tree rõ ràng và functional composition.
- Viết API gateways/facades với nhiều predicates tùy biến cần kiểm thử đường routing chi tiết.
- Muốn giữ business handlers thành Spring beans thuần và gom routing trong một configuration class.
- Hệ thống dùng DSL/functions mạnh, thích tách route table khỏi logic.
- Tái sử dụng functional filters theo nhóm endpoints.

### Những lúc annotation thường phù hợp hơn

- Dự án controller-based lớn đã có conventions, validations, `@ControllerAdvice`, annotations và OpenAPI tooling.
- Nhiều DTOs, form validation, binding/cookies/multipart/model attributes và cần tự động mapping method arguments.
- Đội nhóm cần code dễ đọc với `@GetMapping`, `@PreAuthorize`, `@Valid` và các IDE tooling quen thuộc.
- Migration sang functional sẽ làm tăng mã parse/validation/error handling thủ công nhưng không mang lợi ích rõ rệt.

**Không có yêu cầu phải chuyển toàn bộ ứng dụng.** Hai mô hình có thể tồn tại song song, chỉ cần giữ mapping paths không đè nhau và kiểm thử security/exception/CORS behavior.

## 10. Project runnable: cùng một API bằng WebMvc.fn và @RestController

Ta tạo một ứng dụng Spring Boot có:
- Functional endpoints dưới `/fn/books` và `/fn/search`.
- Annotated endpoints tương đương dưới `/ann/books`.
- Một service lưu books trong RAM, có `AtomicLong` sinh ID, `ConcurrentHashMap` lưu entries.
- JSON request body `{"title":"Spring MVC"}` với Jakarta `@NotBlank`.
- Functional validation do handler chủ động gọi `jakarta.validation.Validator`.
- Annotated validation thông qua `@Valid @RequestBody`.
- Functional filter giả lập chặn request khi `X-Demo-Block: true`, chỉ để hiểu short-circuit.
- Một functional route `/fn/books/latest` đặt **trước** `/fn/books/{id}` để thể hiện route order.

Kết quả là ứng dụng có thể build/test với Java 17+ và Maven. Không có database, session hoặc authentication; các API chỉ phục vụ học tập.

### 10.1. Cây thư mục

```text
webmvc-fn-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/example/webfn/
    │       ├── WebFnApplication.java
    │       ├── Book.java
    │       ├── NewBook.java
    │       ├── ApiError.java
    │       ├── BookStore.java
    │       ├── BookHandler.java
    │       ├── FunctionalRoutes.java
    │       └── AnnotatedBookController.java
    └── test/
        └── java/example/webfn/
            └── WebFnTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webmvc-fn-demo</artifactId>
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

**`src/main/java/example/webfn/WebFnApplication.java`**

```java
package example.webfn;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFnApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFnApplication.class, args);
    }
}
```

### 10.2. DTOs dùng chung

**`src/main/java/example/webfn/Book.java`**

```java
package example.webfn;

public record Book(long id, String title) {}
```

**`src/main/java/example/webfn/NewBook.java`**

```java
package example.webfn;

import jakarta.validation.constraints.NotBlank;

public record NewBook(@NotBlank String title) {}
```

**`src/main/java/example/webfn/ApiError.java`**

```java
package example.webfn;

public record ApiError(String code) {}
```

Java 17 `record` có constructors/accessors, Jackson hỗ trợ deserialize/serialize trong Boot 3.3. `@NotBlank` từ Jakarta Validation đảm bảo title không null/empty/whitespace khi **validator được gọi**. DTO record không tự validate chỉ vì có annotation; validation phải được kích hoạt ở pipeline tương ứng.

### 10.3. Service lưu dữ liệu, không phụ thuộc routing style

**`src/main/java/example/webfn/BookStore.java`**

```java
package example.webfn;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class BookStore {

    private final AtomicLong sequence = new AtomicLong();
    private final ConcurrentHashMap<Long, Book> books =
            new ConcurrentHashMap<>();

    public Book create(String title) {
        long id = sequence.incrementAndGet();
        Book book = new Book(id, title.strip());
        books.put(id, book);
        return book;
    }

    public Optional<Book> find(long id) {
        return Optional.ofNullable(books.get(id));
    }

    public List<Book> all() {
        List<Book> result = new ArrayList<>(books.values());
        result.sort(Comparator.comparingLong(Book::id));
        return result;
    }

    public Optional<Book> latest() {
        return all().stream()
                .max(Comparator.comparingLong(Book::id));
    }

    public List<Book> search(String query) {
        String term = query.strip().toLowerCase(
                java.util.Locale.ROOT);
        return all().stream()
                .filter(book -> book.title().toLowerCase(
                        java.util.Locale.ROOT).contains(term))
                .toList();
    }
}
```

`ConcurrentHashMap` và `AtomicLong` chỉ minh họa xử lý nhiều request trong RAM. `latest()` và `search()` quét dữ liệu để đơn giản, không phải thiết kế tối ưu cho hàng triệu records. App restart thì mất state; không có transaction/database.

### 10.4. Functional handler: ServerRequest → ServerResponse

**`src/main/java/example/webfn/BookHandler.java`**

```java
package example.webfn;

import java.net.URI;

import jakarta.validation.Validator;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class BookHandler {

    private final BookStore store;
    private final Validator validator;

    public BookHandler(BookStore store, Validator validator) {
        this.store = store;
        this.validator = validator;
    }

    public ServerResponse listBooks(ServerRequest request)
            throws Exception {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.all());
    }

    public ServerResponse getBook(ServerRequest request)
            throws Exception {
        long id;
        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException invalid) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError("bad_id"));
        }

        Book book = store.find(id).orElse(null);
        if (book == null) {
            return ServerResponse.notFound().build();
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(book);
    }

    public ServerResponse latest(ServerRequest request)
            throws Exception {
        Book book = store.latest().orElse(null);
        if (book == null) {
            return ServerResponse.notFound().build();
        }
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(book);
    }

    public ServerResponse search(ServerRequest request)
            throws Exception {
        String q = request.param("q").orElse("");

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.search(q));
    }

    public ServerResponse createBook(ServerRequest request)
            throws Exception {
        NewBook input = request.body(NewBook.class);

        if (input == null ||
                !validator.validate(input).isEmpty()) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError("invalid_title"));
        }

        Book book = store.create(input.title());
        URI location = URI.create("/fn/books/" + book.id());

        return ServerResponse.created(location)
                .contentType(MediaType.APPLICATION_JSON)
                .body(book);
    }
}
```

**Điểm quan trọng:**

1. `@Component` tạo bean handler, không phải `@RestController`.
2. Không có `@GetMapping` trên class; URI routing nằm ở `FunctionalRoutes`.
3. `request.body(NewBook.class)` kích hoạt converter JSON cho part **toàn body HTTP** (không phải multipart), rồi `validator.validate(input)` chạy Bean Validation chủ động.
4. `request.pathVariable("id")` trả String. Handler tự parse và trả `400` nếu không phải số; khác annotated `@PathVariable long id` được MVC convert trước method invocation.
5. `ServerResponse.notFound().build()` tạo 404 không body; `ServerResponse.created(location)` tạo 201 và header Location.
6. `search` dùng `Optional` từ `request.param("q")` để đặt default rỗng; bản demo trả tất cả nếu query rỗng.
7. Các methods trả ServerResponse và có `throws Exception` vì `request.body(...)`/response building có các checked exceptions theo Servlet API.
8. Validation không thay authentication, authorization hoặc giới hạn input length/complexity. Với app thật, giới hạn title, request body size, số kết quả và kiểm tra quyền.
9. Store/handler dependency injection giống annotated controller; functional không bắt bạn viết toàn bộ logic trong lambda route.

### 10.5. RouterFunction bean, path precedence và filter

**`src/main/java/example/webfn/FunctionalRoutes.java`**

```java
package example.webfn;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.web.servlet.function.RequestPredicates.contentType;
import static org.springframework.web.servlet.function.RouterFunctions.route;

@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
        return route()
                // Thứ tự quan trọng: cụ thể trước path variable.
                .GET("/fn/books/latest", handler::latest)
                .GET("/fn/books/{id}", handler::getBook)
                .GET("/fn/books", handler::listBooks)
                .GET("/fn/search", handler::search)
                .POST("/fn/books",
                        contentType(MediaType.APPLICATION_JSON),
                        handler::createBook)
                .filter((request, next) -> {
                    // Demo filter, KHÔNG phải security control.
                    String blocked = request.headers()
                            .firstHeader("X-Demo-Block");
                    if ("true".equalsIgnoreCase(blocked)) {
                        return ServerResponse
                                .status(HttpStatus.FORBIDDEN)
                                .contentType(MediaType.APPLICATION_JSON)
                                .body(new ApiError("demo_blocked"));
                    }
                    return next.handle(request);
                })
                .build();
    }
}
```

Chỉ một `RouterFunction<ServerResponse>` bean trong ví dụ. Router sẽ được Spring MVC tự phát hiện; không cần viết `@RestController` cho functional routes.

**Route order được kiểm chứng:** `/fn/books/latest` đặt trước `/fn/books/{id}`. Nếu đảo thứ tự, literal `latest` có thể bị truyền vào `getBook` và nhận `bad_id` thay vì chọn latest.

**POST constraint:** Route `POST /fn/books` dùng predicate `contentType(APPLICATION_JSON)`. Body JSON được `ServerRequest.body(NewBook.class)` decode. Nếu Content-Type không khớp, route có thể không match trước khi handler chạy, và status thực tế có thể khác annotated `consumes`. Không tự hứa status 415 cho mọi trường hợp; API contract cần test riêng.

**Functional filter:** Nếu request gửi `X-Demo-Block: true`, router trả `403` trước khi handler chạy. Đây chỉ là marker để kiểm thử short-circuit và phạm vi filter, **không có giá trị bảo mật**. Đối với API thật, dùng Spring Security với authentication/authorization rules; không lấy header tùy ý do client kiểm soát làm quyền.

### 10.6. Annotated controller dùng chung BookStore

**`src/main/java/example/webfn/AnnotatedBookController.java`**

```java
package example.webfn;

import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/ann/books")
public class AnnotatedBookController {

    private final BookStore store;

    public AnnotatedBookController(BookStore store) {
        this.store = store;
    }

    @GetMapping
    public List<Book> list() {
        return store.all();
    }

    @GetMapping("/latest")
    public ResponseEntity<Book> latest() {
        return store.latest()
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/{id}")
    public ResponseEntity<Book> get(@PathVariable long id) {
        return store.find(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping
    public ResponseEntity<Book> create(
            @Valid @RequestBody NewBook input) {
        Book book = store.create(input.title());
        return ResponseEntity.created(
                URI.create("/ann/books/" + book.id()))
                .body(book);
    }
}
```

Điểm đối chiếu:

- `@RestController` + `@RequestMapping` gom các routes theo class.
- `@GetMapping("/{id}")` + `@PathVariable long id` tự convert String thành long; malformed ID được Spring argument resolution xử lý.
- `@Valid @RequestBody NewBook` tích hợp validation theo annotated method, không phải gọi validator trong body method.
- `ResponseEntity<Book>` có status/headers/body, còn functional dùng `ServerResponse`.
- Hai nhóm paths `/ann/books` và `/fn/books` **không trùng nhau**, nên coexist trong một application rõ ràng.
- Cùng `BookStore` chứng minh business logic không cần gắn với routing style. Nếu tạo qua `/ann/books`, có thể đọc qua `/fn/books/{id}` vì dùng cùng store.

### 10.7. Chạy project và xem HTTP response

Tại thư mục `webmvc-fn-demo` với Java 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Đây là hai lệnh tuần tự, không phải một lệnh chạy đồng thời. Sau khi Boot khởi động trên cổng mặc định `8080`:

**Tạo book qua functional route:**

```bash
curl -i -X POST \
  'http://localhost:8080/fn/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Spring MVC"}'
```

HTTP response lần tạo đầu trên server vừa khởi động:

```http
HTTP/1.1 201
Location: /fn/books/1
Content-Type: application/json

{"id":1,"title":"Spring MVC"}
```

`Location` là relative URI reference hợp lệ cho resource vừa tạo, dùng server-owned ID. Trong production, nếu client contract yêu cầu absolute URL, dùng origin/context path đáng tin (ví dụ `ServletUriComponentsBuilder` với forwarded-header trust policy), không tin raw Host từ Internet.

**Lấy resource:**

```bash
curl -i 'http://localhost:8080/fn/books/1'
```

Khi book ID 1 đã tồn tại, body:

```json
{"id":1,"title":"Spring MVC"}
```

**Danh sách:**

```bash
curl -i 'http://localhost:8080/fn/books'
```

Ví dụ:

```json
[{"id":1,"title":"Spring MVC"}]
```

**Tìm kiếm qua query param:**

```bash
curl -G -i 'http://localhost:8080/fn/search' \
  --data-urlencode 'q=Spring'
```

Dự kiến JSON array chứa book có chữ `Spring`, không phân biệt hoa/thường theo cách `BookStore.search` được viết.

**Annotated API tạo thêm book:**

```bash
curl -i -X POST \
  'http://localhost:8080/ann/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Annotated MVC"}'
```

Response lần tạo thứ hai dự kiến:

```http
HTTP/1.1 201
Location: /ann/books/2

{"id":2,"title":"Annotated MVC"}
```

Nếu trong cùng JVM đã chạy tests hoặc tạo thêm books trước đó, ID có thể khác. Điều cần kiểm chứng là status 201, `Location` trỏ đúng resource, body ID khớp.

**Latest functional route:**

```bash
curl -i 'http://localhost:8080/fn/books/latest'
```

Body chứa book có ID lớn nhất tại thời điểm xử lý. Nếu route `/{id}` được khai báo trước `/latest`, có nguy cơ handler nhận `"latest"` làm `id` và trả 400; test phải bắt điều đó.

**Validation lỗi:**

```bash
curl -i -X POST \
  'http://localhost:8080/fn/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"   "}'
```

Functional handler trả:

```http
HTTP/1.1 400
Content-Type: application/json

{"code":"invalid_title"}
```

Annotated endpoint với cùng body cũng có thể trả `400` từ Bean Validation pipeline, nhưng **error body/schema của Boot mặc định không nhất thiết giống** `{"code":"invalid_title"}`. Đừng viết client phụ thuộc vào exact body nếu chưa định nghĩa error contract chung.

**Short-circuit functional filter:**

```bash
curl -i 'http://localhost:8080/fn/books' \
  -H 'X-Demo-Block: true'
```

Dự kiến:

```http
HTTP/1.1 403
Content-Type: application/json

{"code":"demo_blocked"}
```

Header `X-Demo-Block` chỉ dành cho demonstration filter. Nếu gửi header đó tới `/ann/books`, functional filter này **không áp dụng** cho annotated route; security filter chain bên ngoài có quy tắc độc lập nếu được thêm về sau.

## 11. MockMvc tests: functional và annotated coexist

**`src/test/java/example/webfn/WebFnTest.java`**

```java
package example.webfn;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebFnTest {

    @Autowired MockMvc mvc;

    @Test
    void functionalCreateAndRead() throws Exception {
        MvcResult created = mvc.perform(post("/fn/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Function Book\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value("Function Book"))
                .andReturn();

        String uri = created.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(uri);
        assertTrue(uri.matches("/fn/books/[1-9][0-9]*"));

        mvc.perform(get(uri))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.title").value("Function Book"));
    }

    @Test
    void annotatedCreateAndRead() throws Exception {
        MvcResult created = mvc.perform(post("/ann/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Annotation Book\"}"))
                .andExpect(status().isCreated())
                .andReturn();

        String uri = created.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(uri);
        assertTrue(uri.matches("/ann/books/[1-9][0-9]*"));

        mvc.perform(get(uri))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.title").value("Annotation Book"));
    }

    @Test
    void functionalHandlerValidatesDtoExplicitly()
            throws Exception {
        mvc.perform(post("/fn/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"   \"}"))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.code").value("invalid_title"));
    }

    @Test
    void annotatedControllerUsesBeanValidation()
            throws Exception {
        mvc.perform(post("/ann/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"   \"}"))
           .andExpect(status().isBadRequest());
    }

    @Test
    void specificFunctionalRouteIsNotShadowed()
            throws Exception {
        mvc.perform(post("/fn/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Latest Candidate\"}"))
           .andExpect(status().isCreated());

        mvc.perform(get("/fn/books/latest"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.id").isNumber());
    }

    @Test
    void functionalFilterCanShortCircuit()
            throws Exception {
        mvc.perform(get("/fn/books")
                        .header("X-Demo-Block", "true"))
           .andExpect(status().isForbidden())
           .andExpect(jsonPath("$.code").value("demo_blocked"));

        mvc.perform(get("/ann/books")
                        .header("X-Demo-Block", "true"))
           .andExpect(status().isOk());
    }

    @Test
    void functionalSearchReadsQueryParameter()
            throws Exception {
        mvc.perform(post("/fn/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Spring Searchable\"}"))
           .andExpect(status().isCreated());

        mvc.perform(get("/fn/search").param("q", "Spring Searchable"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$[0].title")
                    .value("Spring Searchable"));
    }

    @Test
    void missingBookReturns404ForBothStyles()
            throws Exception {
        mvc.perform(get("/fn/books/99999999"))
           .andExpect(status().isNotFound());
        mvc.perform(get("/ann/books/99999999"))
           .andExpect(status().isNotFound());
    }
}
```

Chạy:

```bash
mvn test
```

Class khai báo **8 test methods**. Nếu mọi tests pass, Maven exit code `0` và có summary tương tự `Tests run: 8, Failures: 0, Errors: 0, Skipped: 0`. Nội dung này được thiết kế/kiểm tra tĩnh cho Java 17 + Spring Boot 3.3.5, **không tuyên bố đã chạy Maven trong quá trình soạn bài**.

### Đặc điểm của tests

- Dùng `@SpringBootTest` + `@AutoConfigureMockMvc` để đi qua MVC infrastructure, không chỉ gọi Java handler trực tiếp.
- Tests tạo book đọc lại `Location` thực, không hardcode ID = 1 hoặc dựa vào thứ tự tests.
- Functional validation assert body `invalid_title` vì handler chủ động tạo response.
- Annotated validation chỉ assert status `400` vì hình dạng default error body còn phụ thuộc Boot/error handling.
- Filter test cho thấy scope chỉ ở functional routes được builder tạo, không tự áp vào annotated controller.
- Route order test bảo đảm URL literal `/latest` không bị `/{id}` bắt trước.
- Shared `BookStore` có state; test search dùng phrase cụ thể để không phụ thuộc list size nếu có books khác.
- MockMvc không giả lập mọi behavior của ingress/proxy, HTTP timeouts hoặc full security filter chain production. Cần bổ sung integration tests khi thêm authentication, CORS, forwarded headers, file upload/streaming.

## 12. Validation và exception policy cho hệ thống thật

Trong annotated style, framework tự điều khiển nhiều bước: type conversion, method argument validation, `@Valid`, `BindingResult`, method return values và `@ControllerAdvice`. Functional style giữ hạ tầng MVC nhưng **handler chịu trách nhiệm rõ hơn** đối với input parsing và ứng xử lỗi của mình.

### 12.1. Dùng Jakarta Validator

Đối với record:

```java
public record NewBook(
        @NotBlank
        @Size(max = 120)
        String title) {}
```

Nếu muốn một body error thống nhất trong functional handler:

```java
Set<ConstraintViolation<NewBook>> violations =
        validator.validate(input);

if (!violations.isEmpty()) {
    return ServerResponse.badRequest()
            .body(new ApiError("invalid_book"));
}
```

Đây là snippet cần imports `jakarta.validation.Validator`, `ConstraintViolation`, `java.util.Set` và record đã có. Nên dùng **stable machine-readable codes** cho client; tránh trả raw rejected values hoặc exception messages chứa PII. Với annotated controller, có thể dùng `@RestControllerAdvice` và handlers của Bean Validation exceptions để đưa lỗi về cùng schema, nhưng phải kiểm thử thật khi cả hai route models coexist.

### 12.2. Type conversion vs business validation

Annotated `@PathVariable long id` sẽ bị MVC conversion framework xử lý nếu ID không phải số. Functional `request.pathVariable("id")` nhận String và việc `Long.parseLong` nằm trong handler. Hai trường hợp đều có thể kết thúc HTTP 400, nhưng **exception class, điểm bắt lỗi và error body khác nhau**.

Đừng bắt `Exception` rộng trong functional filter rồi luôn trả 400 — điều này có thể che bug server/DB và khiến 5xx bị biến thành 4xx. Hãy phân biệt bad input, not found, authorization, conflict, downstream failure, timeout.

### 12.3. Transaction, DI và tests không biến mất

Functional handler class vẫn có constructor injection, có thể gọi Spring `@Service`, `@Transactional` trên service và Spring Security auth context như bất kỳ controller nào. Không nên đặt transaction trên mọi functional lambda hoặc tự gọi persistence trực tiếp từ route config. Business logic nên nằm ở service để dễ chia sẻ, tái sử dụng và test.

## 13. Security: Servlet Filter và functional filter không giống nhau

Khi ứng dụng có Spring Security:

```text
HTTP Request
  |
  v
Spring Security FilterChain
  - authentication
  - authorization
  - CSRF (khi phù hợp)
  - session/cookie protection
  |
  v
DispatcherServlet
  |
  +--> Annotated controllers
  |
  +--> WebMvc.fn RouterFunction
          |
          +--> HandlerFilterFunction (module policies)
          |
          +--> HandlerFunction
```

**Không đặt toàn bộ security ở functional filter**: nếu một annotated endpoint nằm ngoài router, filter đó sẽ không chạy; nếu có static resources/admin endpoints, cũng có thể không chịu filter. Dùng Spring Security path authorization và method/service-level checks cho business permissions.

### CORS

WebMvc.fn có cơ chế CORS qua Servlet `CorsFilter`; đừng mặc định `@CrossOrigin` gắn trên một annotated controller sẽ tự áp vào functional routes khác. Có thể cấu hình CORS ở Servlet filter/Spring Security theo topology. CORS **không phải authentication**, chỉ giới hạn browser cross-origin reads theo HTTP policy; non-browser clients vẫn có thể gửi request.

### CSRF

Với cookie/session authentication, POST functional route vẫn có CSRF risk giống annotated `@PostMapping`. Spring Security CSRF policy nằm ở security filter chain, không phụ thuộc cách route có annotation hay lambda. Không tắt CSRF chỉ để `curl` demo chạy khi thêm login thật.

### Host và Location header

`ServerResponse.created(URI)` tạo Location nhưng URI vẫn phải đến từ nguồn đáng tin. Nếu dùng request host/forwarded headers để dựng absolute URL, reverse proxy phải strip/sanitize untrusted headers để tránh host-header poisoning/phishing. Demo dùng relative `/fn/books/{id}` cố ý tránh tin host tùy ý.

## 14. CORS, content negotiation, route predicates và errors

Khi annotated controller khai báo:

```java
@GetMapping(path = "/ann/books",
            produces = MediaType.APPLICATION_JSON_VALUE)
```

Spring sẽ dùng mapping conditions và content negotiation của annotated infrastructure. Functional equivalent có thể là:

```java
.GET("/fn/books",
        accept(MediaType.APPLICATION_JSON),
        handler::listBooks)
```

Nhưng các trường hợp request không phù hợp predicate **không nhất thiết trả cùng status** với annotated mapping, dù cả hai dùng DispatcherServlet. Khi xây API cần hợp đồng 404/405/406/415 rõ ràng, hãy test mỗi tổ hợp:

- Path tồn tại, HTTP method khác (405 hay not matched?).
- `Accept` không chấp nhận JSON.
- `Content-Type` sai hoặc thiếu với POST.
- Body JSON malformed.
- JSON hợp lệ nhưng DTO constraints fail.
- Authorization/CSRF rejection xảy ra ở filter trước router.
- Conditional requests `If-None-Match`, ETag, caching/Range.
- OPTIONS/preflight CORS, HEAD và path trailing slash.

Không đem test passes của annotated controller áp thẳng làm "bằng chứng" functional router cũng xử lý 100% giống vậy. Ứng dụng có thể đặt error contract bằng exceptions/filters/advice/custom mappings nếu cần nhất quán.

## 15. Ứng dụng thực tế: tổ chức package và refactor

Một cấu trúc maintainable cho functional MVC:

```text
example.book/
├── api/
│   ├── BookRoutes.java       # RouterFunction beans, predicates, filter composition
│   ├── BookHandler.java      # Request -> Response, validation/HTTP errors
│   ├── NewBook.java          # DTO inbound
│   └── BookView.java         # DTO outbound nếu cần
├── application/
│   └── BookService.java      # Business rules
├── domain/
│   └── Book.java
└── infrastructure/
    └── BookRepository.java
```

Route config nên **ngắn**: path grouping, method predicates, filter configuration. Không nên nhồi hàng trăm dòng JDBC, file I/O, auth policy vào một lambda dài trong `@Bean RouterFunction`. Handler class nên nhận dependencies qua constructor injection, delegating xuống service; validation và response contract có thể được gom thành helper có test.

Với annotated controller, package tương tự nhưng `BookController.java` thường vừa khai báo paths vừa làm HTTP adaptation qua annotations. Functional giúp tách route table rõ nhưng có thể tạo nhiều Java files cho API nhỏ; đó là trade-off, không phải ưu/nhược điểm tuyệt đối.

### Không share mutable RouterFunction builder xuyên request

`RouterFunctions.route()` cho builder dùng khi khởi tạo bean; `build()` ra RouterFunction. Đừng lưu builder mutable trong singleton rồi thay route graph khi có request. Dynamic routing ở runtime cần kiến trúc riêng và đồng bộ hóa. Cũng đừng tạo RouterFunction mới mỗi HTTP request; khai báo bean tại startup.

### OpenAPI và documentation

Nhiều OpenAPI generators/springdoc integrations phát hiện annotated endpoints và `@Operation` metadata dễ hơn. Functional routes cũng có thể được hỗ trợ tùy tool/version hoặc yêu cầu explicit route documentation; cần kiểm chứng công cụ cụ thể, không suy diễn. Nếu migration lớn, kiểm thử OpenAPI output lẫn client SDK contract và security schemes trước khi chuyển.

## 16. Một số use case đáng giá và giới hạn

### 16.1. Gateway/facade với nhiều predicates

Một facade có thể có routes dựa vào path, Accept, Content-Type và custom headers. Functional route composition làm predicates/traversal order rõ. Tuy nhiên nếu nó thực hiện HTTP calls blocking, router DSL vẫn chạy synchronous — hãy thiết kế downstream timeouts, connection pooling, cancellation và circuit breakers.

### 16.2. Static resources

WebMvc.fn có hỗ trợ phục vụ `Resource` qua router utilities, phù hợp một số trường hợp SPA fallback/custom routes. Không nên tự viết một catch-all functional route quá sớm làm che `/api/**`, 404 hoặc security routes. Với static assets thông thường, Spring MVC static resource handlers đã giải quyết nhiều việc như caching, ETag và byte ranges; chọn cơ chế đơn giản phù hợp.

### 16.3. SSE/streaming

Spring MVC có async response APIs, WebMvc.fn cũng có một số response facilities theo phiên bản. Nhưng một functional route lambda **không tự chứng minh** streaming end-to-end non-blocking. Muốn phục vụ SSE hàng nghìn clients hoặc backpressure phức tạp, phải kiểm tra MVC vs WebFlux, network write behavior, executor resource usage, reconnect và timeout — đây là lựa chọn kiến trúc khác với router style.

### 16.4. API versioning

Với `/api/v1` và `/api/v2`, functional route grouping bằng `path("/api/v1",...)` thuận tiện. Với annotation dùng type-level `@RequestMapping("/api/v1")`. Cả hai vẫn cần contract tests cho version routing và backward compatibility; không phải cứ đổi path prefix là toàn bộ model/service/schema đã tương thích.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| `RouterFunction` bean không có effect | Khai báo sai type/package, bean không scan, không dùng Spring MVC infrastructure | Xác nhận `org.springframework.web.servlet.function` và Spring-managed bean |
| Dùng WebFlux `ServerResponse.bodyValue(...)` | Import nhầm `org.springframework.web.reactive.function.server` | Trong WebMvc.fn dùng `ServerResponse.ok().body(...)` |
| `GET /books/latest` thành `bad_id` | Route `/{id}` đứng trước `/latest` | Đặt literal route trước, test ordering |
| `@Valid` không tự kiểm tra body trong functional handler | Chỉ gọi `request.body(...)` mà quên validate | Chủ động dùng Validator/appropriate binding |
| POST JSON returns 404 thay vì 415 | `contentType` predicate không match | Xem request predicate semantics và error contract |
| `@ControllerAdvice` không bao phủ hết lỗi functional | Error handling path khác annotated argument flow | Test malformed JSON, conversion, uncaught exceptions |
| Header route filter chặn annotated controllers? Không | Functional filter chỉ áp vào router tương ứng | Dùng security Servlet filter chain nếu cần toàn app |
| CORS preflight bị chặn | Chỉ dựa `@CrossOrigin` annotated | Thiết kế `CorsFilter`/Security CORS cho functional endpoints |
| CSRF POST lỗi sau khi thêm Security | CSRF vẫn áp dụng với session endpoints | Gửi token hợp lệ, không tắt policy tùy tiện |
| Route ngắn nhưng business logic rối | Mọi logic bị nhồi vào lambda | Tách Handler/Service/Repository |
| Functional không nhanh hơn annotated | Cùng Servlet MVC, blocking I/O vẫn blocking | Benchmark/đo service/downstream bottlenecks |
| API OpenAPI thiếu endpoints | Tool không phát hiện functional routes mặc định | Verify docs generator/version/integration |
| Không nhận header Accept mong muốn | Nhầm `accept` với `contentType` | Inspect HTTP request và predicates |
| Hai nhóm annotation/functional cùng URL | HandlerMapping precedence không rõ | Tránh route overlap; test framework-specific order |
| Error response không nhất quán | Validation/errors xử lý ở hai pipeline khác nhau | Định nghĩa shared error DTO và tests |
| Route filter ghi response nhưng không chạy handler | `next.handle` không được gọi | Kiểm tra short-circuit intentional hay bug |
| Response Location trỏ host lạ | Tin Host/Forwarded từ client | Trusted proxy, canonical base URL hoặc relative URI |
| Trả 201 trong JSON nhưng HTTP status 200 | Quên dùng `ServerResponse.created` | Assert actual HTTP status/Location trong MockMvc |
| DTO từ input chứa field quyền hạn | Mass assignment/over-posting | DTO allowlist, server-side user/tenant auth |
| Test chỉ gọi Handler trực tiếp, mapping vẫn lỗi | Không test DispatcherServlet route predicates | MockMvc + integration tests |

Cách debug hệ thống:

1. Xác nhận đúng namespace `web.servlet.function` và router là bean được Spring scan.
2. Dò request HTTP method/path/headers và thứ tự routes thực tế.
3. Nếu `latest` fail, kiểm tra wildcard/variable route đứng trước hay sau.
4. Kiểm tra `Content-Type` cho POST JSON và `Accept` cho GET.
5. Xác nhận `request.body(Dto.class)` có converter và data type hợp lệ.
6. Phân biệt parse exception, validation errors và handler business errors.
7. Kiểm tra filter scope, việc gọi `next.handle(request)` và security chain.
8. Test cả functional và annotated paths, nhất là nếu ứng dụng kết hợp cả hai.
9. Khi có reverse proxy, kiểm tra forwarded headers, context path, CORS và Location.
10. Đo real latency/throughput trước khi kết luận đổi routing style giúp hiệu năng.

## 18. Checklist đưa WebMvc.fn vào sản phẩm

1. Chọn WebMvc.fn vì nhu cầu route composition/maintainability, không vì tưởng non-blocking.
2. Tất cả Spring MVC functional classes dùng `org.springframework.web.servlet.function`.
3. Đặt routes cụ thể trước routes có placeholders/wildcards.
4. Viết tests cho route collisions và thứ tự khi có nhiều router beans.
5. Dùng constructor injection cho handler, tách service/repository.
6. Đọc body qua converters; khai báo Content-Type/Accept expectations đúng.
7. Kích hoạt Bean Validation tường minh trong functional handler.
8. Chuẩn hóa JSON errors/status/Location và kiểm thử bằng MockMvc.
9. Không dùng functional filter thay Spring Security filter chain.
10. CORS/CSRF/auth/tenant rules được kiểm tra từ HTTP bên ngoài.
11. Không tin request Host/Forwarded headers khi dựng redirects/absolute URLs.
12. Không đặt business logic blocking dài trên Servlet thread chỉ vì route là lambda.
13. Kiểm tra compatibility của OpenAPI/Actuator/tracing tools.
14. Khi migration, không chuyển toàn bộ chỉ để thay annotations — đo chi phí và benefits.
15. Có integration tests cho proxy/Servlet runtime nếu production deployment phức tạp.
16. Không tạo builders/routers động mỗi request khi không có yêu cầu rõ.

## 19. Bài tập tự kiểm tra

1. `RouterFunction` khác `HandlerFunction` như thế nào?
2. `ServerRequest.body(MyDto.class)` và `@RequestBody MyDto` dùng chung cơ chế converter nào, khác nhau ở đâu?
3. Vì sao `/books/latest` phải đứng trước `/books/{id}` trong functional route builder?
4. `ServerResponse.created(location)` đặt HTTP status/header gì?
5. `@NotBlank` trong DTO tự chạy khi functional handler gọi `request.body(...)` không?
6. Vì sao WebMvc.fn chạy trên DispatcherServlet nhưng không phải WebFlux.fn?
7. `accept(APPLICATION_JSON)` khác `contentType(APPLICATION_JSON)` về request header nào?
8. Functional `filter` và Servlet `Filter` khác phạm vi áp dụng thế nào?
9. Nếu một filter không gọi `next.handle(request)` thì chuyện gì xảy ra?
10. Tại sao `HandlerFunction` có thể block Servlet thread dù được viết bằng lambda?
11. Khi migrate annotated sang functional, test những gì với 400/404/405/406/415?
12. Vì sao nên tránh trùng URL giữa annotated controller và functional routes?
13. Có thể dùng một Spring `@Service` cho cả hai loại handler không?
14. WebMvc.fn có tự tạo OpenAPI docs đầy đủ như annotated controllers trong mọi generator không?
15. Nếu thêm Spring Security, functional POST có chịu CSRF policy của app không?

**Gợi ý đáp án:** (1) Router chọn handler, handler xử lý request thành response. (2) Cùng MVC converters nhưng functional đọc tường minh còn annotation method argument resolution. (3) First-match order. (4) 201 + Location. (5) Không tự động, cần validator/binding chính xác. (6) Servlet package/sync pipeline khác reactive. (7) Accept header vs Content-Type body header. (8) Router group vs Servlet/filter chain scope. (9) Short-circuit. (10) Blocking API vẫn block. (11) Route predicates, media types, validation, exceptions và security. (12) Không dự đoán HandlerMapping cross-style precedence. (13) Có, như BookStore demo. (14) Phụ thuộc tooling. (15) Có, theo security config.

## 20. Tài liệu chính thức

- [Spring Framework — Functional Endpoints, Servlet MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-functional.html)
- [Spring Framework 6.1 — RouterFunction Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/function/RouterFunction.html)
- [Spring Framework 6.1 — RouterFunctions Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/function/RouterFunctions.html)
- [Spring Framework 6.1 — ServerRequest Javadoc (Servlet)](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/function/ServerRequest.html)
- [Spring Framework 6.1 — ServerResponse Javadoc (Servlet)](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/function/ServerResponse.html)
- [Spring Framework 6.1 — HandlerFunction Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/function/HandlerFunction.html)
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html)
- [Spring Framework — Spring MVC DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html)
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC Testing with MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)

**Tổng kết:** WebMvc.fn là mô hình functional routing và handling trong **Spring MVC Servlet**, nơi `RouterFunction`/`RequestPredicate` chọn `HandlerFunction` nhận `ServerRequest` rồi trả `ServerResponse`. Nó thay cách khai báo routing/HTTP adapter, **không thay DispatcherServlet hoặc biến blocking I/O thành reactive**. Khác biệt cần nhớ nhất so với annotated controllers là **thứ tự route matching**, **cách lấy/validate tham số tường minh**, **functional filter scope** và **cách quản lý error contract**. Có thể chạy cả hai phong cách cạnh nhau, nhưng nên bảo vệ behavior bằng MockMvc tests và giữ security/validation/business logic tách bạch.

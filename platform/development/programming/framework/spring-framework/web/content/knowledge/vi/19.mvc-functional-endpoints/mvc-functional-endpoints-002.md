# ServerRequest, ServerResponse và HandlerFunction trong Spring Web MVC Functional Endpoints

## 1. Functional MVC giải quyết bài toán gì?

Trong Spring MVC quen thuộc, ta thường khai báo `@RestController`, `@GetMapping`, `@PostMapping`. Spring quét các annotation để chọn handler cho từng HTTP request. Ngoài mô hình đó, **Spring Web MVC còn có WebMvc.fn**, một API theo kiểu **functional endpoints**: ta mô tả route bằng function và xử lý request bằng Java lambda hoặc method reference.

Hợp đồng cốt lõi là:

- `ServerRequest`: abstraction **đầu vào**, cung cấp HTTP method, URI, query/path parameters, headers, cookies và việc đọc/bind body.
- `HandlerFunction<ServerResponse>`: **hàm xử lý**, nhận một `ServerRequest` và trả một `ServerResponse`.
- `ServerResponse`: abstraction **đầu ra**, biểu diễn status, headers, cookies và body; được dựng bằng builder (immutable contract).
- `RouterFunction<ServerResponse>`: **quy tắc chọn hàm**; nhận request rồi trả về `Optional<HandlerFunction<ServerResponse>>` khi match.

Một phép ghép đơn giản:

```java
HandlerFunction<ServerResponse> sayHello =
        request -> ServerResponse.ok().body("Xin chào");

RouterFunction<ServerResponse> router =
        RouterFunctions.route(
                RequestPredicates.GET("/hello"), sayHello);
```

Đây là đoạn code minh họa để hiểu chữ ký. Ví dụ Spring Boot hoàn chỉnh có thể chạy ở mục 10.

**Điểm rất quan trọng:** WebMvc.fn chạy trên **Servlet stack** với `DispatcherServlet`. Nó **không phải** WebFlux.fn; không cần Reactor `Mono`/`Flux` để sử dụng ba thành phần này. API Servlet có package:

```java
org.springframework.web.servlet.function.ServerRequest
org.springframework.web.servlet.function.ServerResponse
org.springframework.web.servlet.function.HandlerFunction
org.springframework.web.servlet.function.RouterFunction
org.springframework.web.servlet.function.RouterFunctions
org.springframework.web.servlet.function.RequestPredicates
```

WebFlux.fn dùng `org.springframework.web.reactive.function.server.*` và các chữ ký bất đồng bộ như `Mono<ServerResponse>`. Import nhầm hai hệ sẽ dẫn tới lỗi compile hoặc kỳ vọng sai về cách đọc body.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác quan hệ `RouterFunction → HandlerFunction → ServerResponse`.
2. Đọc route parameters, query parameters, headers và JSON body từ `ServerRequest`.
3. Trả 200, 201 với Location, 204, 400, 404 và JSON bằng `ServerResponse` builder.
4. Soạn `RouterFunctions.route()`, hiểu thứ tự đánh giá routes, `RequestPredicates`, lồng path và composition.
5. Sử dụng `HandlerFilterFunction`/`before`/`after` mà không nhầm với Servlet Filter hoặc Spring Security.
6. Tách routing với business logic, validation, transaction, lỗi và security; biết giới hạn của functional style.
7. Xây một ứng dụng Spring Boot 3 + Java 17 có route list/search/get/create/delete và 9 bài kiểm thử MockMvc.

Bài học áp dụng cho Spring Framework 6.x / Spring Boot 3.x với Java 17+. Java records được dùng để viết DTO ngắn gọn.

## 2. Luồng hoạt động dưới DispatcherServlet

WebMvc.fn không tạo một web server thứ hai. Nó dùng cùng cơ sở hạ tầng Servlet MVC với annotated controllers:

```text
Browser/API client
     │ HTTP GET /api/notes/1
     ▼
Servlet filters (security, logging, ...)
     │
     ▼
DispatcherServlet
     │
     ▼
HandlerMapping chain
     ├── RouterFunctionMapping
     │      └── RouterFunction<ServerResponse>
     │             ├── xét RequestPredicate của route
     │             └── trả HandlerFunction nếu match
     │
     ├── RequestMappingHandlerMapping
     │      └── annotated @GetMapping/@PostMapping...
     │
     └── các HandlerMapping khác
     │
     ▼
HandlerFunctionAdapter
     │
     ▼
HandlerFunction.handle(ServerRequest)
     ├── đọc request
     ├── gọi service/repository
     └── tạo ServerResponse
     │
     ▼
ServerResponse.writeTo(...) / HTTP converters
     ▼
HTTP status + headers + body
```

Sơ đồ là lược đồ lý luận, **không khẳng định RouterFunctionMapping luôn có order cao hơn RequestMappingHandlerMapping** trong mọi Spring/Boot configuration. Các HandlerMapping có `order` và setup riêng; khi một URL có hai loại handler cạnh tranh, cần xem actual HandlerMapping order, tránh cùng khai báo một đường dẫn trong functional và annotated controllers.

Trong setup Spring Boot MVC thông thường, bạn chỉ cần:

```java
@Bean
RouterFunction<ServerResponse> routes(NoteHandlers handlers) {
    return RouterFunctions.route()
            .GET("/api/notes", handlers::list)
            .GET("/api/notes/{id}", handlers::get)
            .build();
}
```

Spring tự tìm `RouterFunction<?>` beans, ghép/đăng ký thông qua `RouterFunctionMapping` và sử dụng `HandlerFunctionAdapter` để gọi handler. Không bắt buộc tự cấu hình một Servlet khác. `spring-boot-starter-web` thường đủ để bật hạ tầng WebMvc.fn.

### 2.1. So với @RestController

Annotated style:

```java
@RestController
class NoteController {
    @GetMapping("/api/notes/{id}")
    Note get(@PathVariable long id) {
        return service.find(id);
    }
}
```

Functional style:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/api/notes/{id}", handlers::get)
                .build();
```

Chức năng cuối có thể giống nhau, nhưng responsibilities khác:

| Annotated MVC | WebMvc.fn |
| --- | --- |
| Annotation trên class/method quyết định mapping | `RouterFunction` và `RequestPredicate` quyết định mapping |
| Parameters được bind thành method arguments | `ServerRequest` cung cấp phương thức truy cập |
| Return DTO/ResponseEntity | Trả `ServerResponse` |
| Logic thường đặt trong controller method | Logic trong lambda/handler class |
| Advice/validation/integration có convention của annotated MVC | Cần hiểu cụ thể WebMvc.fn binding/exception/filter pipeline |
| Có thể cùng tồn tại trên DispatcherServlet | Có thể cùng tồn tại với annotated controllers |

WebMvc.fn không tự tăng tốc mọi endpoint hoặc làm blocking JDBC thành non-blocking. Giá trị chính là **route definitions composable**, behavior biểu diễn bằng functions và separation rõ ràng giữa route mapping và handler logic.

## 3. HandlerFunction: một hàm xử lý một request

Về bản chất, chữ ký API có thể hiểu như:

```java
@FunctionalInterface
public interface HandlerFunction<T extends ServerResponse> {
    T handle(ServerRequest request) throws Exception;
}
```

Đây là **trích yếu chữ ký** để học, không phải toàn bộ source code Spring. Lambda:

```java
HandlerFunction<ServerResponse> hello = request ->
        ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body("Hello from WebMvc.fn");
```

Một class handler thường dễ bảo trì hơn nhiều lambdas lớn:

```java
class NoteHandlers {
    ServerResponse list(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(List.of("Spring", "MVC"));
    }

    ServerResponse health(ServerRequest request) {
        return ServerResponse.ok().body("OK");
    }
}
```

Code trên minh họa methods được tham chiếu bởi `handlers::list`, `handlers::health`. Trong dự án đầy đủ, handler được tạo thành Spring component, inject service và đưa vào RouterFunction bean.

### 3.1. HandlerFunction không nhất thiết là Spring bean

Lambda có thể tạo trong bean route; handler class có thể là Spring `@Component`, một object được tự tạo hoặc phụ thuộc được cung cấp qua DI. Điều quan trọng là `RouterFunction` chứa một reference tới handler hợp lệ.

Tuy nhiên, **không tự `new Service()` khắp nơi** nếu service cần transaction/security/configuration do Spring quản lý. Tách dependencies và inject qua constructor giúp kiểm thử tốt hơn.

### 3.2. Checked exceptions

`HandlerFunction#handle` cho phép ném `Exception`. Phương thức handler đọc JSON body có thể khai báo `throws Exception`:

```java
ServerResponse create(ServerRequest request) throws Exception {
    CreateNote command = request.body(CreateNote.class);
    return ServerResponse.ok().body(command);
}
```

Đây chỉ là ví dụ cú pháp; trong production, phải validate command và xử lý lỗi decode/validation theo error contract. Không trả stack trace hoặc raw persistence exception cho client.

## 4. ServerRequest: đọc HTTP request qua một interface

`ServerRequest` là façade phía handler cho Servlet HTTP request. Một số nhóm API thường dùng:

| Nhu cầu | API điển hình | Đầu ra |
| --- | --- | --- |
| Method | `request.method()` | `HttpMethod` |
| URI đầy đủ | `request.uri()` | `URI` |
| Path | `request.path()` | Request path string |
| Query một giá trị | `request.queryParam("q")` | `Optional<String>` |
| Toàn query params | `request.params()` | `MultiValueMap<String,String>` |
| Path variable | `request.pathVariable("id")` | `String` |
| Headers | `request.headers()` | `ServerRequest.Headers` |
| Header đơn | `request.headers().firstHeader("X-Request-Id")` | String hoặc null |
| Body kiểu class | `request.body(CreateNote.class)` | DTO từ `HttpMessageConverter` |
| Body generic | `request.body(new ParameterizedTypeReference<List<Note>>() {})` | `List<Note>` |
| Servlet request gốc | `request.servletRequest()` | `HttpServletRequest` |
| Bind params | `request.bind(Foo.class, binder -> ...)` | Object qua binder |

Một số methods có thể throw exception khi không có path variable hoặc input không parse được. `ServerRequest` giúp code functional thuận tiện hơn, **không bỏ qua** HTTP semantics, converters hoặc validation.

### 4.1. Path parameters

Route:

```java
RouterFunctions.route()
    .GET("/api/notes/{id}", handlers::get)
    .build();
```

Handler:

```java
ServerResponse get(ServerRequest request) {
    String raw = request.pathVariable("id");
    long id;
    try {
        id = Long.parseLong(raw);
    } catch (NumberFormatException ex) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("error", "invalid_id"));
    }

    return service.find(id)
            .map(note -> ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(note))
            .orElseGet(() -> ServerResponse.notFound().build());
}
```

Đây là snippet minh họa, không phải method standalone vì `service` chưa được khai báo. Bài hoàn chỉnh sẽ dùng ConcurrentHashMap để không phụ thuộc DB.

**Lưu ý:** `ServerRequest.pathVariable("id")` trả string, không tự động thực hiện type conversion y hệt `@PathVariable long id` trên annotated controller. Handler phải parse và quyết định response lỗi theo contract.

### 4.2. Query params

```java
String q = request.queryParam("q").orElse("");
String trimmed = q.trim();
```

Nếu query có nhiều giá trị, `request.params()` cho phép đọc danh sách. Phân biệt:

- `pathVariable("id")` từ `/{id}` trong route.
- `queryParam("q")` từ `?q=spring`.
- `headers().firstHeader("...")` từ HTTP headers.
- `body(...)` từ request entity.

Không đọc `request.body(...)` hai lần một cách ngẫu nhiên: Servlet request body stream thông thường không được tự động rewind. Sử dụng DTO một lần rồi truyền DTO vào service.

### 4.3. Headers và content negotiation

```java
MediaType requested =
        request.headers().accept().stream()
                .findFirst()
                .orElse(MediaType.ALL);

String correlation =
        request.headers().firstHeader("X-Request-Id");
```

Snippet minh họa cách truy cập; server không nhất thiết phải lấy media type đầu tiên để quyết định response trong mọi tình huống. Dùng `RequestPredicates.accept(MediaType.APPLICATION_JSON)` hoặc Spring HTTP converters khi muốn negotiation rõ hơn.

Đừng coi một header như `X-User-Role` do client tự gửi là bằng chứng phân quyền. Headers có thể bị giả bởi non-browser clients; authentication/authorization phải dựa trên trust boundary và Spring Security.

### 4.4. Đọc JSON body

Với `spring-boot-starter-web`, Jackson và MVC converters thường hỗ trợ JSON:

```java
record CreateNote(String title) {}

ServerResponse create(ServerRequest request) throws Exception {
    CreateNote data = request.body(CreateNote.class);

    if (data == null || data.title() == null ||
            data.title().isBlank()) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("error", "title_required"));
    }

    return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(data);
}
```

Snippet này có thể đặt trong một handler class cùng record; Java 17 hỗ trợ record. Khi JSON sai cú pháp hoặc content type không được converter hỗ trợ, Spring có thể ném lỗi parse/media type để tầng exception handling xử lý.

**Không mặc định cho rằng** `@Valid` đặt trên record type hoặc argument của một `HandlerFunction` sẽ tự tạo `BindingResult` như annotated controller. Functional endpoint cần kiểm tra validation một cách **tường minh**, hoặc dùng binder/validator tích hợp phù hợp.

### 4.5. Bind form/query params

Spring MVC Functional API có:

```java
FormInput input = request.bind(
        FormInput.class,
        binder -> binder.setAllowedFields("title", "category"));
```

Đoạn trên minh họa binder, cần `FormInput` là một class bindable có properties tương ứng. `setAllowedFields(...)` hữu ích để giảm **mass assignment** khi bind từ request parameters; cần hiểu cách binding/validation errors được báo về handler hoặc MVC exception resolution.

Với JSON body, hãy dùng DTO request riêng, không deserialize thẳng entity persistence chứa các fields như role, ownerId, paymentStatus rồi lưu không kiểm soát.

## 5. ServerResponse: dựng status, headers và body

`ServerResponse` có immutable-style contract. Ta không mutate một response đã “build” theo ý muốn; thường gọi static builder để tạo response:

```java
ServerResponse response = ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .header("X-Demo", "webmvc-fn")
        .body(Map.of("status", "ready"));
```

Các static entrypoints thường gặp:

| Mục tiêu | Ví dụ |
| --- | --- |
| 200 OK có body | `ServerResponse.ok().body(data)` |
| 200 JSON | `ServerResponse.ok().contentType(APPLICATION_JSON).body(data)` |
| 201 Created | `ServerResponse.created(location).body(resource)` |
| 204 No Content | `ServerResponse.noContent().build()` |
| 400 Bad Request | `ServerResponse.badRequest().body(error)` |
| 404 Not Found | `ServerResponse.notFound().build()` |
| 401/403/409/422... | `ServerResponse.status(HttpStatus.CONFLICT).body(error)` |
| Redirect | `ServerResponse.temporaryRedirect(uri).build()` |
| Header tùy ý | Builder `.header("X-Key", "value")` |
| Content type | Builder `.contentType(MediaType.APPLICATION_JSON)` |

### 5.1. 200 với body

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(Map.of("id", 12, "name", "Example"));
```

Kết quả JSON dự kiến:

```json
{"id":12,"name":"Example"}
```

Thứ tự keys của JSON object không phải contract mặc định; kiểm thử từng field thay vì so chuỗi byte-for-byte.

### 5.2. 201 + Location

```java
URI location = URI.create("/api/notes/12");
return ServerResponse.created(location)
        .contentType(MediaType.APPLICATION_JSON)
        .body(new Note(12, "Created"));
```

Một response “create” tốt thường có status `201 Created` và `Location` trỏ tới URL của tài nguyên mới. Trong sản phẩm thật, tùy yêu cầu URI có thể là absolute (host/context path đúng qua reverse proxy) hoặc relative như demo; không ghép host từ header không tin cậy.

### 5.3. 204 và body rỗng

```java
return ServerResponse.noContent().build();
```

HTTP 204 không có representation body. Không gắn nội dung JSON vào response rồi kỳ vọng browser nhận body ở 204.

### 5.4. Response body không tự là WebFlux Publisher

Ở WebMvc.fn:

```java
ServerResponse.ok().body(note);
```

Đây là Servlet MVC API. WebFlux.fn thường viết một `Mono<ServerResponse>` hoặc response builder với `bodyValue(...)` tùy API. Một số async adapters có hỗ trợ cho body async trong WebMvc.fn, **nhưng không suy ra API Servlet giống hệt reactive stack**. Nếu ứng dụng cần non-blocking end-to-end, cần xét stack, các dependencies và contract riêng.

## 6. RouterFunction: request được chuyển cho HandlerFunction nào?

Một router là function chọn handler. Với builder:

```java
@Bean
RouterFunction<ServerResponse> routes(NoteHandlers handler) {
    return RouterFunctions.route()
            .GET("/api/notes/search", handler::search)
            .GET("/api/notes/{id}", handler::get)
            .GET("/api/notes", handler::list)
            .POST("/api/notes", handler::create)
            .DELETE("/api/notes/{id}", handler::delete)
            .build();
}
```

**Thứ tự trong RouterFunction có ý nghĩa.** Spring mô tả routes được đánh giá theo thứ tự; route đầu tiên match được chọn. Vì vậy đặt `GET /api/notes/search` **trước** `GET /api/notes/{id}`, nếu không string `search` có thể bị xem là `id`, dẫn tới 400/404 trong handler sai.

### 6.1. Các RequestPredicate tiêu biểu

Có thể match không chỉ URL mà còn method, Accept, Content-Type:

```java
import static org.springframework.web.servlet.function.RequestPredicates.*;

RouterFunction<ServerResponse> router = RouterFunctions.route()
    .GET("/api/notes", accept(MediaType.APPLICATION_JSON),
         handler::list)
    .POST("/api/notes", contentType(MediaType.APPLICATION_JSON),
          handler::create)
    .build();
```

Đây là ví dụ cấu hình **khác** với routes của project chạy ở mục 10. Predicate có thể kết hợp:

```java
RequestPredicate predicate =
        RequestPredicates.GET("/api/notes")
                .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));
```

Khi predicate không match, RouterFunction có thể thử route tiếp; nếu không route nào match, Servlet MVC tìm handler khác và có thể trả 404/405/406/415 tùy mapping/converters và hạ tầng. **Đừng khẳng định mọi HTTP content-type lỗi luôn được WebMvc.fn tự trả đúng 415**, nhất là khi POST route có `contentType` predicate mà không match.

### 6.2. Nested routes

Khi nhiều endpoints chung prefix, có thể nhóm:

```java
return RouterFunctions.route()
    .path("/api/notes", builder -> builder
        .GET("/search", handler::search)
        .GET("/{id}", handler::get)
        .GET(handler::list)
        .POST(handler::create))
    .build();
```

Đoạn này là cấu hình thay thế cho routes dùng absolute path; không tạo đồng thời cả hai để tránh mapping trùng. Khi nesting, cần hiểu path rỗng và slash trong builder; nếu muốn tránh nhầm giữa `/api/notes` và `/api/notes/`, cấu hình và test đúng URL thực tế.

### 6.3. Compose RouterFunctions

Có thể ghép nhiều nhóm routes:

```java
RouterFunction<ServerResponse> apiRoutes = ...;
RouterFunction<ServerResponse> adminRoutes = ...;

RouterFunction<ServerResponse> all =
        apiRoutes.and(adminRoutes);
```

Hoặc builder `.add(otherRouter)`, `.andRoute(predicate, handler)`. Thứ tự ghép có nghĩa vì các router functions được đánh giá tuần tự; tránh catch-all pattern quá sớm.

### 6.4. Cùng tồn tại nhiều RouterFunction bean

`RouterFunctionMapping` có thể tự tìm các RouterFunction beans, sắp xếp và kết hợp. Với nhiều beans có overlapping paths, cần order rõ và test kết quả; đừng giả định tên bean hay thứ tự file Java quyết định precedence. Trong một nhóm API vừa phải, một router bean cho từng domain/module thường đủ minh bạch.

### 6.5. RouterFunctionMapping order khác thứ tự route trong builder

Có hai tầng:

1. **Giữa HandlerMappings:** các mapping MVC/annotations/static resources có order riêng.
2. **Bên trong RouterFunction:** các routes trong một function được thử theo thứ tự khai báo/compose.

Một URL có functional route cụ thể nhưng HandlerMapping khác được chọn trước có thể không bao giờ tới router đó. Không nhầm “đặt route cụ thể lên đầu” với việc đổi `HandlerMapping#order` toàn MVC.

## 7. HandlerFilterFunction: behavior trước/sau HandlerFunction

WebMvc.fn có middleware kiểu functional qua `HandlerFilterFunction`. Filter nhận:

- `ServerRequest request`.
- `HandlerFunction<ServerResponse> next`.

Nó có thể xử lý request trước, gọi `next.handle(request)`, quan sát response, hoặc **không gọi next** để trả response sớm.

Ví dụ filter minh họa:

```java
.filter((request, next) -> {
    if ("reject".equals(
            request.headers().firstHeader("X-Demo-Flow"))) {
        return ServerResponse.status(
                HttpStatus.TOO_MANY_REQUESTS)
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("error", "demo_filtered"));
    }
    return next.handle(request);
})
```

Trong project hoàn chỉnh, đây là **tình huống demo để kiểm tra middleware có thể short-circuit**, **không phải authorization/filter bảo mật production**. Client có thể tự chọn header X-Demo-Flow, vì vậy không dùng nó làm quyết định user identity hoặc rate limiting thật.

### 7.1. before và after

Builder còn có `before` và `after`:

```java
.before(request ->
        ServerRequest.from(request)
                .header("X-Internal-Hint", "demo")
                .build())
.after((request, response) -> {
    // logging/observability (tránh log dữ liệu nhạy cảm)
})
```

Ví dụ này mô tả API, chưa hoàn chỉnh một RouterFunction độc lập. `before` có thể cung cấp một ServerRequest wrapper tùy biến cho downstream; `after` phù hợp quan sát nhẹ sau handler. Không dùng hook để tốn CPU lớn hoặc viết vào HttpServletResponse khi response đã commit.

**Trong nested routes**, filter đặt bên trong nested builder chỉ áp dụng nhóm con tương ứng, khác với filter đặt ở root builder áp dụng tất cả routes trong root. Hãy test scope filter bằng URL ngoài/ trong nhóm.

### 7.2. So với Servlet Filter và HandlerInterceptor

| Công cụ | Layer | Phạm vi |
| --- | --- | --- |
| Servlet `Filter` | Container, trước DispatcherServlet | Theo URL/dispatcher mapping, có thể áp dụng rộng |
| MVC `HandlerInterceptor` | Spring MVC handler chain | Trước/sau handler MVC phù hợp |
| WebMvc.fn `HandlerFilterFunction` | Bên trong RouterFunction | Chỉ các routes được wrap |
| Spring Security `SecurityFilterChain` | Security Servlet filters | Authentication, authorization, CSRF, headers... |
| `@ControllerAdvice` | MVC error/binding/response handling | Khác phạm vi và hỗ trợ tùy handler adapter |

Trong production, authentication/authorization nên do Spring Security đảm nhiệm, không tự dùng một request header và HandlerFilterFunction để thay thế. Middleware functional có ích để áp dụng logic domain-specific, enrichment nhẹ hoặc custom error mapping cho route group.

## 8. Validation, exceptions và persistence

### 8.1. Validation với DTO

Functional handler đọc body:

```java
CreateNote input = request.body(CreateNote.class);
```

Việc decode thành Java record **không bảo đảm tất cả Bean Validation constraints tự chạy như một annotated method có `@Valid @RequestBody`**. Lựa chọn:

- Với rule đơn giản, validate minh bạch trong handler/service (như demo `title` không blank, max length).
- Với rules phức tạp, inject `jakarta.validation.Validator` hoặc Spring `org.springframework.validation.Validator` và chuyển violations thành error response ổn định.
- Với form/query binding, xem `ServerRequest.bind(...)` và `DataBinder` để giới hạn fields.

Một đoạn dùng Jakarta Bean Validation (cần starter-validation và validator bean):

```java
Set<ConstraintViolation<CreateNote>> violations =
        validator.validate(input);

if (!violations.isEmpty()) {
    return ServerResponse.badRequest()
            .contentType(MediaType.APPLICATION_JSON)
            .body(Map.of("error", "validation_failed"));
}
```

Đây là snippet minh họa, không có đủ class/import để chạy độc lập. Với ứng dụng thật, nên gom violations thành trường/constraint messages có thể localize, không trả raw sensitive values.

### 8.2. Lỗi parse body và lỗi nghiệp vụ khác nhau

| Tình huống | Cách xử lý hợp lý |
| --- | --- |
| JSON sai syntax | 400 nếu MVC converter/handler mapping xử lý theo error policy |
| JSON đúng syntax nhưng field title blank | 400 với error code `title_required` |
| ID path không parse long | 400 với error code `invalid_id` |
| ID hợp lệ nhưng không tìm thấy | 404 |
| Conflict vì resource đã tồn tại | 409 nếu contract quy định |
| Content-Type không được hỗ trợ | 415 nếu Framework/converter contract áp dụng |
| User đã login nhưng thiếu quyền | 403 qua Spring Security |
| Lỗi DB/remote service | 5xx có structured error, không leak stack trace |

Trong annotated MVC, `@ExceptionHandler`/`@ControllerAdvice` có tích hợp quen thuộc với controller methods. Với functional endpoints, cần **test thực tế** cách exceptions đi qua `HandlerFunctionAdapter` và MVC exception resolvers; nếu muốn xử lý tất cả domain errors trong một route group, `HandlerFilterFunction` có thể catch domain exceptions rồi dựng `ServerResponse` tương ứng. Đừng giả định annotation-based binding errors và mọi handler advice áp dụng tự động 100% giống nhau.

### 8.3. Transaction boundaries

Router/handler không thay thế service layer. Ví dụ lưu một note vào DB:

```java
@Service
class NoteService {
    @Transactional
    public Note create(CreateNote command) {
        // validate ownership, convert DTO, persist through repository
        // and return saved object
    }
}
```

Đoạn minh họa thiếu model/repository và không standalone. Trong project thật, service method transactional cần được gọi qua Spring proxy phù hợp, và validations/authorization trên resource vẫn phải thực thi khi ghi.

### 8.4. OpenAPI, observability và filters

Một số tools tự nhận diện annotated controllers sâu hơn functional endpoints. Nếu dùng OpenAPI generator/documentation plugins, cần kiểm tra phiên bản có support `RouterFunction`/functional routes hay không, hoặc khai báo docs bổ sung. Instrumentation/logging thường vẫn có Servlet Filter/Spring MVC chain, nhưng custom metrics cần xác định matched route/handler đúng.

## 9. Security, caching và HTTP semantics

WebMvc.fn **không tự cung cấp authentication, authorization, CSRF hoặc session management**. Nó chia sẻ Servlet security/filter chain với Spring MVC.

- **Authentication:** ai là user? Dựa trên Spring Security/OIDC/Session/Bearer hợp lệ.
- **Authorization:** user có quyền đọc/sửa note với ID cụ thể và tenant phù hợp không?
- **CSRF:** state-changing methods khi browser dùng cookie/ambient credentials cần policy đúng.
- **CORS:** JavaScript từ origin nào có thể đọc response? WebMvc.fn reference khuyến nghị dedicated `CorsFilter` cho functional endpoints khi cần.
- **Validation:** không đưa DTO tùy ý vào entity; chống mass assignment.
- **Caching:** GET có thể dùng ETag/Cache-Control khi representation thích hợp; 304 không tự bỏ query DB nếu validator tính muộn.
- **Idempotency:** GET là safe; DELETE/PUT có idempotent semantics phù hợp; POST create có thể sinh duplicate nếu retry, cần idempotency key ở nghiệp vụ nếu cần.
- **Content negotiation:** `Accept` và `Content-Type` là những header khác nhau; test preflight/CORS và converter nếu API được gọi từ browser.

### 9.1. Không mở endpoint mutation vô điều kiện trong production

Demo cố tình cho phép POST/DELETE để tập trung vào ServerRequest/ServerResponse; trong ứng dụng thật phải thêm Spring Security, kiểm tra quyền theo resource/tenant và CSRF khi phù hợp. Đừng copy bộ demo lên internet như API production mà không có các lớp kiểm soát này.

### 9.2. Lỗi CORS không phải lỗi routing

Nếu browser báo CORS, không vội sửa `RouterFunction.GET(...)`. Kiểm tra `OPTIONS` preflight, allowed origins/methods/headers và Spring Security filter order. HTTP client ngoài browser có thể gọi route dù browser JavaScript không được đọc response; CORS không thay authentication.

### 9.3. Đừng cho client quyết định ID/owner một cách mù quáng

Khi POST body:

```json
{"title":"My note","ownerId":"other-user","role":"ADMIN"}
```

Nếu handler chỉ dùng `CreateNote(String title)`, những fields không thuộc contract không nên được sử dụng để đặt ownership/quyền. Trong sản phẩm thật, chính sách xử lý unknown JSON properties cần được định nghĩa, và identity của owner phải lấy từ principal đáng tin cậy, không từ body.

## 10. Demo hoàn chỉnh: Spring Boot 3, Java 17, functional CRUD

Ứng dụng nhỏ có:

- `GET /api/notes`: danh sách Notes theo ID.
- `GET /api/notes/search?q=Spring`: tìm theo title; đặt route `search` trước `{id}`.
- `GET /api/notes/{id}`: trả một note hoặc 400/404.
- `POST /api/notes`: nhận JSON `{"title":"..."}`, validate, trả 201 + Location.
- `DELETE /api/notes/{id}`: xóa, trả 204 hoặc 404.
- `HandlerFilterFunction` kiểm tra một **demo header** và có thể trả 429 (không phải security control).
- `GET /annotated/ping` dùng `@RestController` để chứng minh hai style cùng chạy trong một ứng dụng.

Dùng Spring Boot **3.3.13**, Java **17+**, Maven. Data store dùng `ConcurrentHashMap` và `AtomicLong` để không cần cài DB; dữ liệu sẽ mất khi ứng dụng restart.

### 10.1. Cấu trúc project

```text
webmvc-fn-demo/
├── pom.xml
└── src/
    ├── main/java/example/FnMvcApplication.java
    └── test/java/example/FnMvcApplicationTest.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>webmvc-fn-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
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
```

### 10.3. FnMvcApplication.java

Toàn bộ code dưới đây nằm trong một file. Chỉ main class là public top-level class; DTO records là public nested types, giúp Jackson đọc/ghi dễ dàng. `NoteHandlers` và `RouteConfig` là package-private classes được Spring component scan tìm thấy.

```java
package example;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@SpringBootApplication
public class FnMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(FnMvcApplication.class, args);
    }

    public record Note(long id, String title) {}
    public record CreateNote(String title) {}
}

@Configuration
class RouteConfig {

    @Bean
    RouterFunction<ServerResponse> noteRoutes(NoteHandlers handler) {
        return RouterFunctions.route()
            // Cụ thể trước; /search không bị route /{id} bắt.
            .GET("/api/notes/search", handler::search)
            .GET("/api/notes/{id}", handler::get)
            .GET("/api/notes", handler::list)
            .POST("/api/notes", handler::create)
            .DELETE("/api/notes/{id}", handler::delete)
            .filter((request, next) -> {
                // Chỉ để học cơ chế short-circuit,
                // KHÔNG dùng header này cho security.
                String mode = request.headers()
                        .firstHeader("X-Demo-Flow");
                if ("reject".equals(mode)) {
                    return ServerResponse.status(
                            HttpStatus.TOO_MANY_REQUESTS)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of("error", "demo_filtered"));
                }
                return next.handle(request);
            })
            .build();
    }
}

@Component
class NoteHandlers {

    private final Map<Long, FnMvcApplication.Note> notes =
            new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(2);

    NoteHandlers() {
        notes.put(1L, new FnMvcApplication.Note(1L, "Spring MVC"));
    }

    ServerResponse list(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(sortedNotes(""));
    }

    ServerResponse search(ServerRequest request) {
        String q = request.queryParam("q")
                .orElse("")
                .trim()
                .toLowerCase(Locale.ROOT);

        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(sortedNotes(q));
    }

    private List<FnMvcApplication.Note> sortedNotes(String query) {
        return notes.values().stream()
                .filter(note -> note.title()
                        .toLowerCase(Locale.ROOT).contains(query))
                .sorted(Comparator.comparingLong(
                        FnMvcApplication.Note::id))
                .toList();
    }

    ServerResponse get(ServerRequest request) {
        Long id = parseId(request);
        if (id == null) {
            return badId();
        }

        FnMvcApplication.Note note = notes.get(id);
        if (note == null) {
            return ServerResponse.notFound().build();
        }
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }

    ServerResponse create(ServerRequest request) throws Exception {
        FnMvcApplication.CreateNote command =
                request.body(FnMvcApplication.CreateNote.class);

        if (command == null || command.title() == null ||
                command.title().isBlank()) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("error", "title_required"));
        }

        String title = command.title().trim();
        if (title.length() > 120) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("error", "title_too_long"));
        }

        long id = nextId.getAndIncrement();
        FnMvcApplication.Note note =
                new FnMvcApplication.Note(id, title);
        notes.put(id, note);

        return ServerResponse.created(
                    URI.create("/api/notes/" + id))
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }

    ServerResponse delete(ServerRequest request) {
        Long id = parseId(request);
        if (id == null) {
            return badId();
        }

        FnMvcApplication.Note removed = notes.remove(id);
        return removed != null
                ? ServerResponse.noContent().build()
                : ServerResponse.notFound().build();
    }

    private Long parseId(ServerRequest request) {
        try {
            return Long.valueOf(request.pathVariable("id"));
        } catch (NumberFormatException ex) {
            return null;
        }
    }

    private ServerResponse badId() {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("error", "invalid_id"));
    }
}

@RestController
class PingController {
    @GetMapping("/annotated/ping")
    Map<String, String> ping() {
        return Map.of("style", "annotated");
    }
}
```

#### Giải thích từng vai trò

**FnMvcApplication:** bật Spring Boot và định nghĩa hai Java records. `Note` là response DTO; `CreateNote` là request DTO chỉ chấp nhận title ở tầng handler.

**RouteConfig:** bean `noteRoutes` là entrypoint đăng ký functional endpoints. Spring tự detect bean, không cần tự instantiate `RouterFunctionMapping`. Static route `/search` đứng trước variable route `/{id}`. `HandlerFilterFunction` ở cuối builder áp dụng cho routes thuộc builder này; header demo chỉ dùng để chứng minh filter có thể không gọi next.

**NoteHandlers:** chứa business logic đơn giản của từng route. Nó đọc `ServerRequest`, parse query/path/body rồi trả `ServerResponse` với status và content type rõ. `ConcurrentHashMap` bảo đảm thao tác map cơ bản an toàn khi nhiều request, nhưng **không** thay thế database transaction, policy cho nhiều tenants hoặc idempotency của POST.

**PingController:** chứng minh annotated style và functional style dùng chung DispatcherServlet. Không đăng ký hai handlers cùng URL để tránh bài toán precedence ngoài trọng tâm.

### 10.4. Chạy ứng dụng

Tại thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Yêu cầu Maven/JDK 17+ và kết nối để tải dependencies nếu chúng chưa có ở local repository.

Gọi GET:

```bash
curl -i http://localhost:8080/api/notes
curl -i http://localhost:8080/api/notes/1
curl -i "http://localhost:8080/api/notes/search?q=Spring"
curl -i http://localhost:8080/annotated/ping
```

Các body JSON kỳ vọng trong trạng thái ứng dụng mới khởi động:

```json
[{"id":1,"title":"Spring MVC"}]
```

GET ID 1:

```json
{"id":1,"title":"Spring MVC"}
```

Search:

```json
[{"id":1,"title":"Spring MVC"}]
```

Annotated ping:

```json
{"style":"annotated"}
```

Create:

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H "Content-Type: application/json" \
  -d '{"title":"WebMvc.fn"}'
```

Kết quả dự kiến ở app mới chạy và chưa có POST khác: status 201, header `Location: /api/notes/2` và body:

```json
{"id":2,"title":"WebMvc.fn"}
```

Nếu có nhiều POST, số ID sẽ tăng; **không** hardcode ID 2 vào client production. Dùng Location thực được server trả.

Bad request:

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H "Content-Type: application/json" \
  -d '{"title":"   "}'
```

Kỳ vọng HTTP 400 với JSON:

```json
{"error":"title_required"}
```

Xóa:

```bash
curl -i -X DELETE http://localhost:8080/api/notes/2
```

Kỳ vọng 204 nếu ID 2 tồn tại ở server đang chạy. Sau đó `GET /api/notes/2` trả 404. Demo không có database nên restart app sẽ đưa seed ID 1 trở lại.

Filter demo:

```bash
curl -i http://localhost:8080/api/notes \
  -H "X-Demo-Flow: reject"
```

Kỳ vọng status 429 và:

```json
{"error":"demo_filtered"}
```

Đây là **middleware demonstration**; header do client gửi không có ý nghĩa bảo mật. Các lệnh cURL dùng nối dòng của POSIX shell; trên Windows PowerShell dùng `curl.exe` và cách xuống dòng tương ứng.

## 11. MockMvc: kiểm thử functional routes thật sự

Sử dụng Spring Boot test context vì `@SpringBootTest` nạp `RouterFunctionMapping`, `HandlerFunctionAdapter`, handlers và converters. `@AutoConfigureMockMvc` cho phép gọi MVC mà không cần mở cổng network. Mỗi test chỉ assert contract cần thiết, không phụ thuộc thứ tự JSON keys.

File `src/test/java/example/FnMvcApplicationTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FnMvcApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void seededNoteCanBeRead() throws Exception {
        mvc.perform(get("/api/notes/1"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.title").value("Spring MVC"));
    }

    @Test
    void listContainsSeededNote() throws Exception {
        mvc.perform(get("/api/notes"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].id").value(1));
    }

    @Test
    void specificSearchRoutePrecedesIdVariable() throws Exception {
        mvc.perform(get("/api/notes/search")
                    .param("q", "spring"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$[0].title").value("Spring MVC"));
    }

    @Test
    void invalidPathIdGives400() throws Exception {
        mvc.perform(get("/api/notes/not-a-number"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_id"));
    }

    @Test
    void unknownIdGives404() throws Exception {
        mvc.perform(get("/api/notes/999999"))
            .andExpect(status().isNotFound());
    }

    @Test
    void createReturns201LocationAndReadableResource()
            throws Exception {
        MvcResult created = mvc.perform(post("/api/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"A new note\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    HttpHeaders.LOCATION,
                    startsWith("/api/notes/")))
            .andExpect(jsonPath("$.title").value("A new note"))
            .andReturn();

        String location = created.getResponse()
                .getHeader(HttpHeaders.LOCATION);

        mvc.perform(get(location))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("A new note"));
    }

    @Test
    void blankTitleIsRejected() throws Exception {
        mvc.perform(post("/api/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"  \"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error")
                    .value("title_required"));
    }

    @Test
    void functionalFilterCanShortCircuit() throws Exception {
        mvc.perform(get("/api/notes")
                    .header("X-Demo-Flow", "reject"))
            .andExpect(status().isTooManyRequests())
            .andExpect(jsonPath("$.error").value("demo_filtered"));
    }

    @Test
    void annotatedAndFunctionalHandlersCoexist() throws Exception {
        mvc.perform(get("/annotated/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.style").value("annotated"));
    }
}
```

Các tests không giả định ID mới luôn bằng 2; case create lấy `Location` từ response rồi GET resource mới. Test list chỉ assert note seeded ở vị trí đầu vì danh sách được sort theo ID. Nếu tích hợp test parallelization hoặc stateful persistence thật, cần data isolation/cleanup rõ.

**Test thứ tự route rất quan trọng:** `/api/notes/search` phải match route tường minh trước `/api/notes/{id}`; nếu đảo thứ tự, handler get có thể parse chữ `search` thành số và trả 400, làm test search thất bại.

### 11.1. Bổ sung bài test DELETE

Để xác nhận 204 và 404 sau xóa mà không dựa vào seeded resource:

```java
@Test
void deleteCreatedNote() throws Exception {
    MvcResult created = mvc.perform(post("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"title\":\"Delete me\"}"))
        .andExpect(status().isCreated())
        .andReturn();

    String url = created.getResponse()
            .getHeader(HttpHeaders.LOCATION);

    mvc.perform(delete(url))
        .andExpect(status().isNoContent());

    mvc.perform(get(url))
        .andExpect(status().isNotFound());
}
```

Đặt method này vào class test phía trên để có đủ imports đã khai báo. Khi đó suite có **10 tests**. Nội dung main application đã hỗ trợ route DELETE.

### 11.2. MockMvc kiểm thử được gì, không kiểm thử được gì?

MockMvc xác nhận route registration/selection, HTTP converters, response status/body và composition theo Spring MVC. Nó không mô phỏng đầy đủ TLS, reverse proxy, Servlet container actual network buffering, connection timeouts hay browser CORS enforcement.

Với ứng dụng production, thêm các bài integration tests chạy embedded server trên random port để kiểm tra forwarded headers, network status, caching, cookie, filter mapping và Spring Security thật.

## 12. Gỡ lỗi WebMvc.fn theo từng tầng

### 12.1. Route không match

Tình huống:

```text
GET /api/notes/search → 400 invalid_id
```

Nguyên nhân hay gặp: `GET /api/notes/{id}` đứng trước route `search`. Sửa bằng cách đặt route cụ thể trước. Đừng đoán rằng Spring sẽ tự chọn route cụ thể nhất như ở annotated RequestMapping.

### 12.2. Chọn nhầm WebFlux import

Nếu IDE auto-import:

```java
org.springframework.web.reactive.function.server.ServerRequest
```

thì code của bạn đang dùng type reactive, không phù hợp với `org.springframework.web.servlet.function.RouterFunction`. Sửa package nhất quán theo WebMvc.fn; không chèn `Mono<ServerResponse>` vào method handler đồng bộ rồi kỳ vọng compile.

### 12.3. JSON body không đọc được

Checklist:

1. `spring-boot-starter-web` có Jackson JSON converter phù hợp không?
2. Client có gửi `Content-Type: application/json` không?
3. Body JSON có đúng syntax và schema DTO không?
4. Record/class có constructors/accessors để converter tạo object không?
5. Handler có đọc body một lần hay đã tiêu thụ stream trước?
6. Khi binder lỗi, server có chuyển exception thành error response với code rõ ràng không?

### 12.4. Functional filter gây 429 không mong muốn

Nếu filter ở root builder, mọi routes xây từ builder có thể chịu filter đó. Kiểm tra predicate/header và scope. Nếu muốn áp cho một nhóm con, dùng nested builder/filter đúng vị trí thay vì lọc root quá rộng.

### 12.5. CORS hoặc 401/403 xuất hiện

Chúng có thể đến từ Servlet/Spring Security layers trước khi handler chạy. Không sửa route để “cho qua” security. Kiểm tra CORS preflight, authentication, roles/ownership và CSRF cùng configured filter chain.

### 12.6. Đường URL trả 404 từ static ResourceHandler

Trong Spring Boot, static resource handler có thể match wildcard `/**` sau khi không có controller/functional route. Vì vậy 404 có thể là “resource not found” thay vì “không có handler nào”, tùy configuration. Gỡ lỗi theo HandlerMapping được chọn, không chỉ HTTP status.

### 12.7. Response không có Content-Type JSON

Chỉ trả Map/object mà không đặt content type có thể để message converter chọn mặc định theo Accept negotiation; để API demo ổn định, chúng ta dùng `.contentType(MediaType.APPLICATION_JSON)` trên các JSON responses. Với application thực, thiết kế Accept/produces behavior rõ ràng.

### 12.8. Performance không tăng sau khi chuyển từ @RestController

WebMvc.fn là cách **biểu đạt routing/handling**, không bảo đảm query nhanh hơn, DB non-blocking hoặc lượng object allocations ít hơn đáng kể. Profiling DB latency, serialization, request concurrency, CPU và garbage collection trước khi quyết định refactor.

## 13. Lỗi phổ biến và cách tránh

| Nhầm lẫn | Hậu quả | Hướng đúng |
| --- | --- | --- |
| “WebMvc.fn chính là WebFlux.fn” | Import sai, kỳ vọng Mono/Flux | Dùng Servlet package cho WebMvc.fn |
| “HandlerFunction tự chọn URL” | Thiếu routing bean, endpoint 404 | Đăng ký RouterFunction bean |
| “RouterFunction là controller method” | Không phân biệt routing với handling | Router chọn handler, handler dựng response |
| “ServerRequest là HttpServletRequest y hệt” | Bỏ qua wrapper/convenience API | Dùng ServerRequest, chỉ xuống servletRequest khi cần |
| “ServerResponse giống HttpServletResponse mutable” | Mutate sai contract | Dùng immutable-style builder |
| “GET /{id} sau /search cũng tự ưu tiên search” | Search bị parse làm ID | Đặt route cụ thể trước trong RouterFunction |
| “Dùng body DTO là tự @Valid” | Invalid data đi vào service | Validation explicit |
| “Client cho ownerId thì cứ tin” | Mass assignment/IDOR | Ownership từ authenticated context |
| “Middleware filter là Spring Security” | Bỏ sót auth/CSRF | Dùng SecurityFilterChain |
| “Thêm route filter root chỉ ảnh hưởng route gần nhất” | Không mong muốn filter áp cả nhóm | Hiểu scope builder/nesting |
| “404 có nghĩa chắc chắn RouterFunctionMapping không match” | Gỡ lỗi sai layer | Xem HandlerMapping/static fallback |
| “201 không cần Location” | Client khó định vị resource mới | Trả Location khi phù hợp |
| “Trả 204 vẫn có JSON body” | HTTP semantics sai | No content thật sự |
| “Cho POST retry vô tư” | Có thể tạo duplicate | Idempotency key/logic nếu cần |
| “Functional style tự giải quyết error handling” | Leak stack traces/unstructured errors | Định nghĩa error contract và test |
| “Functional API non-blocking end-to-end” | Capacity plan sai | Servlet stack có blocking I/O |
| “@ControllerAdvice áp 100% như @RequestBody” | Validation/advice không như dự kiến | Test adapter/converter/error flow thực tế |
| “Route filter return 429 theo header demo là rate limiting thật” | Security policy sai | Dùng rate limiter thực với identity/trust boundary |
| “Có ConcurrentHashMap là có transaction” | Business race/không persistent | DB transaction, optimistic locking |
| “Test hardcode ID mới = 2” | Flaky khi test order hoặc concurrency | Lấy Location/ID từ response |
| “Kiểm thử body JSON bằng chuỗi y hệt” | Thất bại vô ích do key order | Dùng jsonPath/JSON structural assertions |
| “CORS OK tức user được phép POST” | Nhầm browser policy với authorization | Tách CORS, auth, role, CSRF |

## 14. Checklist áp dụng thực tế

Khi bắt đầu một module WebMvc.fn:

1. **Chọn stack:** chắc chắn là Servlet MVC hay reactive WebFlux, imports nhất quán.
2. **Router structure:** gom routes theo domain, path/method/media predicates minh bạch.
3. **Precedence:** đặt routes cụ thể trước wildcard/path-variable rộng.
4. **Handler functions:** giữ nhỏ, chỉ đọc request, validate, gọi service, dựng response.
5. **DTO schema:** tách request/response DTO khỏi JPA entities; tránh mass assignment.
6. **HTTP status:** GET 200/404, POST 201+Location, DELETE 204, validation 400 và lỗi policy rõ.
7. **Business service:** transactions, optimistic concurrency, ownership checks, multi-tenant isolation.
8. **Security:** CORS/Csrf/Spring Security filters, method/object authorization và private cache policy.
9. **Error mapping:** chuẩn hóa JSON error code, tránh leak stack trace; test body parse/converter errors.
10. **Cross-cutting:** phân biệt HandlerFilterFunction với Servlet Filter/MVC interceptor.
11. **Composition:** tránh nhiều RouterFunction beans overlapping paths mà không biết order.
12. **Concurrency:** kiểm tra thread-safety và resource exhaustion nếu handler gọi blocking services.
13. **Testing:** test static-vs-variable route, 201/Location, 400, 404, 204, functional middleware.
14. **Observability:** ghi route matched, request ID, status, p95 latency, security denials không lộ secrets.
15. **API docs:** xem generator/OpenAPI tooling có hỗ trợ functional routes và khai báo bổ sung nếu cần.

### 14.1. Khi nào nên chọn WebMvc.fn?

Phù hợp khi bạn muốn routes khai báo tập trung, composable predicates, handler classes đơn giản, middleware áp một group, hoặc một codebase ưu tiên functional style.

Không nhất thiết phù hợp nếu cả nhóm đã dùng annotated controllers, validation/exception advice/tools quen thuộc và chuyển style chỉ tăng rủi ro refactor mà không cải thiện rõ readability. **Spring hỗ trợ cả hai**, nên một hệ thống có thể dùng từng style ở module thích hợp.

## 15. Tự kiểm tra

**1.** `HandlerFunction<ServerResponse>` nhận và trả gì?  
**Đáp án:** nhận `ServerRequest` và trả `ServerResponse`.

**2.** `RouterFunction` thực hiện nhiệm vụ gì?  
**Đáp án:** chọn HandlerFunction phù hợp theo predicate/method/path, trả Optional khi match.

**3.** WebMvc.fn có dùng Reactor Mono theo mặc định không?  
**Đáp án:** không; Servlet `HandlerFunction` trả ServerResponse trực tiếp.

**4.** Package ServerRequest của WebMvc.fn là gì?  
**Đáp án:** `org.springframework.web.servlet.function.ServerRequest`.

**5.** Lấy ID từ path variable thế nào?  
**Đáp án:** `request.pathVariable("id")`, rồi parse/validate khi cần.

**6.** Lấy query `?q=java` thế nào?  
**Đáp án:** `request.queryParam("q").orElse("")`.

**7.** Đọc JSON thành DTO thế nào?  
**Đáp án:** `request.body(CreateNote.class)` khi converter hỗ trợ.

**8.** Response 201 có Location làm sao?  
**Đáp án:** `ServerResponse.created(uri).body(object)`.

**9.** Trả 204 không body thế nào?  
**Đáp án:** `ServerResponse.noContent().build()`.

**10.** Tại sao route `/search` phải đứng trước `/{id}`?  
**Đáp án:** RouterFunction xét routes theo thứ tự; first match wins.

**11.** RequestPredicates có thể kiểm tra gì ngoài URL?  
**Đáp án:** HTTP method, Accept, Content-Type và các điều kiện custom.

**12.** `HandlerFilterFunction` khác Servlet Filter thế nào?  
**Đáp án:** middleware của RouterFunction, không có phạm vi toàn Servlet container.

**13.** Dùng `HandlerFilterFunction` để tin `X-User-Role` từ client có an toàn không?  
**Đáp án:** không; authentication/authorization cần trust boundary và Spring Security.

**14.** Có phải Java record với @NotBlank tự được validate khi dùng `request.body(...)`?  
**Đáp án:** không mặc nhiên; cần trigger Validator/binding phù hợp.

**15.** Một bean RouterFunction có cần @EnableWebMvc trên Spring Boot không?  
**Đáp án:** thông thường không; MVC auto-configuration hỗ trợ.

**16.** Functional route và @RestController có thể cùng tồn tại không?  
**Đáp án:** có trên DispatcherServlet, nhưng tránh overlapping URLs không kiểm soát.

**17.** Vì sao `ConcurrentHashMap` không thay thế DB transaction?  
**Đáp án:** map chỉ cung cấp thao tác concurrency ở memory; không có durability/transaction nghiệp vụ.

**18.** Test nào xác nhận functional route không bị `/{id}` bắt nhầm?  
**Đáp án:** GET `/api/notes/search?q=Spring` phải trả danh sách thành công.

**19.** WebMvc.fn có tự làm JDBC non-blocking không?  
**Đáp án:** không; đây là functional routing/handling trên Servlet stack.

**20.** Response 404 có luôn nghĩa không có HandlerFunction matched không?  
**Đáp án:** không; handler có thể tự trả 404, hoặc static fallback báo missing resource.

## 16. Nguồn tham khảo chính thức

- [Spring Framework 6.2 — Web MVC Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): mô hình WebMvc.fn, RouterFunction, HandlerFunction, ServerRequest/Response, predicates, nesting/filtering.
- [Spring Framework 6.2 — Servlet Functional API package](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/function/package-summary.html): interfaces/builder classes.
- [Spring Framework 6.2 — RouterFunctionMapping Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/function/support/RouterFunctionMapping.html): detect/combine RouterFunction beans.
- [Spring Framework 6.2 — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): so sánh Servlet MVC với reactive API, tránh import nhầm.
- [Spring Framework 6.2 — Spring MVC Test Framework](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html): MockMvc testing.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): MVC auto-configuration, Servlet stack.
- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110): status codes và request/response semantics.

**Ghi nhớ:** `RouterFunction` quyết định **route nào phù hợp**; `HandlerFunction` thực hiện **nghiệp vụ/điều phối** trên `ServerRequest`; `ServerResponse` biểu diễn **kết quả HTTP**. Bộ ba này là **functional style trên Spring MVC Servlet**, có thể đứng cạnh annotated controllers và dùng chung Servlet/security infrastructure, nhưng vẫn cần validation, phân quyền, error handling, tests và thiết kế dữ liệu đúng.

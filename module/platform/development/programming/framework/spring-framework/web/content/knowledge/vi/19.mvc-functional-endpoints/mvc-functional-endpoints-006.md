# Kết hợp functional endpoint với hạ tầng Spring MVC hiện có

## 1. Bối cảnh và mục tiêu

Một ứng dụng Spring MVC đang vận hành thường đã có nhiều thành phần: `@RestController`, `@ControllerAdvice`, `HttpMessageConverter`, `WebMvcConfigurer`, Servlet filters, HandlerInterceptors, Spring Security, Jackson, Bean Validation, CORS, static resources, templates, tracing và các bài kiểm thử MockMvc. Khi muốn thêm một module viết theo phong cách functional, câu hỏi không chỉ là "làm sao khai báo RouterFunction?" mà còn là:

- Functional endpoint có chạy chung `DispatcherServlet` với controller annotation không?
- Service, repository, transaction và dependency injection đang có có thể tái sử dụng không?
- JSON converter, locale, validation, CORS, interceptor, security, logging sẽ vận hành ở tầng nào?
- `@ControllerAdvice`, `@Valid`, `@InitBinder`, `@ResponseBody` có tự được áp dụng giống nhau cho handler functional không?
- Có thể khai báo hai nhóm endpoint cạnh nhau mà không xung đột route/HTTP status không?
- Làm sao migrate theo từng bước và kiểm thử không phá hợp đồng API cũ?

**WebMvc.fn** là mô hình functional HTTP endpoints của **Spring MVC Servlet stack**, package `org.springframework.web.servlet.function`. Nó có `RouterFunction`, `HandlerFunction`, `ServerRequest` và `ServerResponse`, nhưng vẫn dùng cùng hạ tầng `DispatcherServlet`. Nó **không phải WebFlux.fn** (package `org.springframework.web.reactive.function.server`) và không tự khiến HTTP/database I/O trở thành non-blocking.

Bài này dùng **Java 17, Spring Boot 3.3.5, Spring Framework 6.1.x**, có ví dụ Maven chạy được với functional + annotated endpoints cùng ứng dụng, dùng chung service và cấu hình MVC. Sau đó phân tích kỹ các ranh giới của converters, validation, errors, filters, CORS, Spring Security, versioning và migration.

### Bạn sẽ làm được gì?

1. Đưa `RouterFunction<ServerResponse>` vào ứng dụng MVC hiện hữu, không tạo `DispatcherServlet` thứ hai.
2. Chạy song song functional routes với `@RestController` trên các URL khác nhau.
3. Dùng chung Spring-managed `@Service`, DTO, validator, Jackson converters và transaction boundaries.
4. Áp dụng MVC-level `HandlerInterceptor`/CORS chung; phân biệt chúng với functional `filter`.
5. Hiểu cơ chế chọn handler, thứ tự routes và rủi ro khi mapping chồng lấn.
6. Thiết kế error response đồng nhất khi argument resolution và validation của hai phong cách khác nhau.
7. Bảo vệ Spring Security, CSRF, authorization, logging và metric không phụ thuộc route style.
8. Viết MockMvc tests cho cả hai loại endpoint và kiểm chứng thay đổi thật.
9. Lập kế hoạch migrate tăng dần, không rewrite toàn bộ chỉ để chuyển cú pháp.

## 2. Một DispatcherServlet, nhiều kiểu handler

Spring MVC được tổ chức quanh `DispatcherServlet`. Nó nhận HTTP request từ Servlet container và hỏi lần lượt các `HandlerMapping` được đăng ký để chọn handler phù hợp; sau đó một `HandlerAdapter` có khả năng sẽ gọi handler đó.

Sơ đồ rút gọn:

```text
HTTP client
     |
     v
Servlet container (Tomcat/Jetty/Undertow)
     |
     v
Servlet Filter chain (security, tracing, request policy)
     |
     v
DispatcherServlet
     |
     +---- RequestMappingHandlerMapping
     |        |
     |        v
     |    @RestController / @GetMapping / @PostMapping
     |        |
     |        v
     |    RequestMappingHandlerAdapter
     |    @RequestBody, @Valid, ResponseEntity...
     |
     +---- RouterFunctionMapping
     |        |
     |        v
     |    RouterFunction + RequestPredicate
     |        |
     |        v
     |    HandlerFunctionAdapter
     |    ServerRequest -> ServerResponse
     |
     +---- Static resource / other HandlerMappings
              |
              v
     HTTP status, headers, body -> Servlet response
```

Với WebMvc.fn, Spring MVC sử dụng các thành phần như `RouterFunctionMapping` và `HandlerFunctionAdapter`. RouterFunctionMapping tìm các `RouterFunction<?>` beans trong application context, sắp xếp và kết hợp để định tuyến. WebMvc.fn và annotated controllers có thể cùng tồn tại trong một ứng dụng Boot Web.

**Điều giống nhau không có nghĩa mọi cơ chế method argument handling đều giống nhau.** Cả hai dùng chung nền tảng MVC và message converters, nhưng functional handler nhận một `ServerRequest` và tự đọc body/params; annotated controller được `RequestMappingHandlerAdapter` resolve các tham số Java dựa vào `@RequestParam`, `@PathVariable`, `@RequestBody`, `@Valid`, v.v.

### Không cần webflux-starter

Ứng dụng chỉ có:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

đã có Spring Web MVC và functional Servlet API cần thiết. **Không import nhầm** các class cùng tên dưới `web.reactive.function.server`. Thêm `spring-boot-starter-webflux` chỉ để viết WebMvc.fn vừa không cần thiết vừa có thể tạo confusion về môi trường/test và reactive clients.

### Không bật @EnableWebMvc tùy tiện trong Spring Boot

Boot auto-configures MVC cùng Jackson, static resources và converter defaults. Việc thêm `@EnableWebMvc`/mở rộng `WebMvcConfigurationSupport` thủ công có thể vô hiệu hóa hoặc thay thế một phần auto-configuration. Để bổ sung interceptor, CORS, formatters hoặc resource handlers, thường bắt đầu bằng `@Configuration implements WebMvcConfigurer` thay vì dựng một MVC stack thứ hai.

## 3. Các thành phần tái sử dụng được và ranh giới áp dụng

| Thành phần hiện có | Functional endpoint dùng lại được? | Điều cần kiểm chứng |
| --- | --- | --- |
| `DispatcherServlet` và Servlet runtime | **Có** | Chỉ một MVC application/context như bình thường |
| Spring `@Service` / `@Repository` / DI | **Có** | Handler là Spring bean, inject qua constructor |
| `@Transactional` ở service | **Có** | Gọi qua Spring proxy; transaction nằm ở service boundary |
| Jackson / `HttpMessageConverter` | **Có** | `request.body(Dto.class)` và `ServerResponse.body(dto)` dùng MVC converters |
| Servlet `Filter` / Spring Security chain | **Có** | Đúng URL/dispatcher types và thứ tự filter chains |
| MVC `HandlerInterceptor` | Có thể áp dụng qua MVC HandlerMapping config | Test filter/interceptor mappings và request lifecycle |
| `WebMvcConfigurer.addCorsMappings` | Có cấu hình CORS theo HandlerMapping | Test preflight và Origin với functional URL |
| `@Valid @RequestBody` method argument magic | **Không tự áp dụng vào HandlerFunction như controller method** | Functional cần validator/binding explicit |
| `@InitBinder` / `@ModelAttribute` method arguments | **Không tự áp dụng cùng cách** | Dùng `ServerRequest` API hoặc custom binding |
| `@ControllerAdvice` / `@ExceptionHandler` | Không bảo đảm xử lý giống mọi lỗi functional | Test từng lỗi, dùng error boundary thích hợp |
| `ResponseBodyAdvice` cho controller method | Không giả định nó biến đổi mọi ServerResponse functional | Test thực tế converter/adapter path |
| Router-level `filter` | Chỉ cho router/nhóm functional tương ứng | Không tự bọc các annotated controllers |
| `@CrossOrigin` trên annotated method | Chỉ metadata của annotated handler | Dùng CORS global/filter phù hợp cho functional routes |
| `@PreAuthorize` trên service method | Có khi Spring method security được bật và gọi qua proxy | Không dựa vào annotation controller method thay full filter-chain auth |
| OpenAPI generator/Actuator/tracing | Phụ thuộc từng integration/version | Verify tài liệu, operation IDs, metrics tags, links |

**Quy tắc kiến trúc:** tái sử dụng các thành phần **nằm dưới routing** (service, repository, transaction) và các thành phần **nằm trước DispatcherServlet** (Servlet Filter/security). Với tính năng dựa trực tiếp vào `HandlerMethod` hay annotation metadata, phải kiểm thử hoặc chuyển sang cơ chế explicit cho functional handlers.

## 4. Dùng chung service và DTO, chỉ thay HTTP adapter

Một thiết kế ổn định:

```text
                      Shared Spring Context
  +------------------------------------------------+
  | DTOs + Bean Validation                         |
  | NoteService (@Service, @Transactional nếu cần) |
  | NoteRepository                                 |
  +------------------------------------------------+
             ^                            ^
             |                            |
  +---------------------+    +------------------------+
  | Annotated adapter   |    | Functional adapter     |
  | @RestController     |    | RouterFunction @Bean   |
  | @RequestBody @Valid |    | HandlerFunction        |
  | ResponseEntity      |    | ServerRequest/Response |
  +---------------------+    +------------------------+
             |                            |
             +---------- HTTP ------------+
```

Ví dụ cả hai REST styles cần "tạo note":

- Annotated controller có `@PostMapping` và tham số `@Valid @RequestBody NewNote input`.
- Functional handler gọi `NewNote input = request.body(NewNote.class)`, rồi tự gọi `validator.validate(input)`.
- Cả hai gọi `NoteStore.create(input.title())` (hoặc một `NoteService` ở hệ thống thật).
- Cả hai trả HTTP `201 Created`, header `Location` và JSON DTO `Note`.

**Đừng copy business rules vào hai handler**. Nếu đã có `@Service` chứa authorization, transaction, idempotency và invariant, để nó là nguồn logic duy nhất. Functional/annotated chỉ nên xử lý những khác biệt ở biên HTTP.

## 5. Route discovery, thứ tự và tránh xung đột

### 5.1. WebMvc.fn dùng thứ tự match

Ví dụ:

```java
RouterFunction<ServerResponse> router = route()
        .GET("/api/fn/notes/latest", handler::latest)
        .GET("/api/fn/notes/search", handler::search)
        .GET("/api/fn/notes/{id}", handler::find)
        .build();
```

Đây là **snippet** (cần bean handler/imports). Routes literal `latest` và `search` được đặt **trước** `/{id}`. Nếu `/{id}` match đầu, nó có thể nhận `id="latest"` và handler parse sai số. Với annotated controllers, Spring dùng ranking theo độ cụ thể của `@RequestMapping`; functional route traversal thường phụ thuộc **order**.

### 5.2. Hai phong cách nên có namespace rõ ràng

Trong lúc thử nghiệm, có thể đặt:

- `/api/annotated/notes/**` cho API annotations hiện hành.
- `/api/fn/notes/**` cho phiên bản functional được phát triển song song.

Trong migration thật, không nhất thiết giữ cả hai public prefixes; có thể chuyển **từng route** tại boundary được kiểm soát. Nhưng tránh khai báo **chính xác cùng HTTP method + path** đồng thời trên RouterFunction và @RestController rồi mong framework "chọn đúng" theo thứ tự Java source. HandlerMapping precedence phụ thuộc cấu hình/framework, không phải một hợp đồng để dựa vào nhằm rollout.

Nếu cần so sánh hai implementations trước khi thay endpoint, có thể:

1. Dùng URL riêng/staging để chạy contract tests.
2. Đặt traffic splitting ở gateway theo quy tắc được kiểm soát và quan sát.
3. Chuyển từng route khi functional handler đạt contract và security checks.
4. Gỡ mapping cũ sau khi migration hoàn tất.

### 5.3. Nhiều RouterFunction beans

`RouterFunctionMapping` có thể phát hiện nhiều RouterFunction beans và kết hợp chúng theo thứ tự. Với modules:

```java
@Bean
RouterFunction<ServerResponse> catalogRoutes(CatalogHandler handler) {
    return route()
            .GET("/api/catalog", handler::list)
            .build();
}

@Bean
RouterFunction<ServerResponse> billingRoutes(BillingHandler handler) {
    return route()
            .GET("/api/billing", handler::summary)
            .build();
}
```

Đây là **snippets** giả định các handlers tương ứng. Nếu các prefixes hoàn toàn khác nhau, thứ tự ít nguy hiểm hơn. Nếu route patterns overlap (catch-all, path variables), phải dùng thứ tự bean/order có chủ đích và tests; đừng dựa vào alphabet/tên class.

## 6. @Bean RouterFunction nằm trong @Configuration

Kiểu tối giản:

```java
@Configuration
class FunctionalNotesConfiguration {

    @Bean
    RouterFunction<ServerResponse> notesRoutes(NoteHandler handler) {
        return route()
                .GET("/api/fn/notes", handler::list)
                .build();
    }
}
```

Đây là snippet; `NoteHandler`/static `route()` được định nghĩa ở ví dụ đầy đủ mục 11. Spring Boot scan `@Configuration`, tạo `RouterFunction` bean khi khởi động; MVC phát hiện và phục vụ HTTP request. Không cần `@RestController` trên `NoteHandler` và không cần tạo DispatcherServlet/Servlet registration khác.

**Quan trọng:** RouterFunctions builder thường được tạo lúc startup; không tạo builder mutable và gắn thêm routes trên mỗi request. Handler đã inject từ Spring bean thường là singleton và được dùng lại, vì vậy đừng giữ `ServerRequest` hoặc dữ liệu user vào mutable instance fields của handler.

## 7. Chung MVC HttpMessageConverters, khác cách gọi

Một cấu hình Spring Boot bình thường có Jackson converter đọc/ghi JSON.

Annotated:

```java
@PostMapping(
        path = "/api/annotated/notes",
        consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<Note> create(
        @Valid @RequestBody NewNote body) {
    // ...
}
```

Functional:

```java
public ServerResponse create(ServerRequest request) throws Exception {
    NewNote body = request.body(NewNote.class);
    // validate body rồi gọi service
    return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(result);
}
```

Cả hai có thể dùng cùng Jackson configuration, nhưng:

- Annotated method `@RequestBody` được một MVC argument resolver gọi trước controller.
- Functional handler **chủ động** gọi `request.body(NewNote.class)`. Với malformed JSON, lỗi có thể phát sinh **bên trong handler** và đi qua error handling khác.
- Annotated `@ResponseBody`/`ResponseEntity` được handler adapter xử lý; functional `ServerResponse` ghi HTTP body theo cơ chế `ServerResponse.writeTo` và converters.
- Cùng converter không đồng nghĩa mọi `RequestBodyAdvice`/`ResponseBodyAdvice` vốn gắn vào annotated method pipeline đều tự chạy cho functional ServerResponse.
- Cả hai cần content-type/Accept negotiation chính xác; functional route có thể dùng `contentType(MediaType.APPLICATION_JSON)` predicate.

**Cẩn thận với custom converters:** Nếu team dùng `WebMvcConfigurer.configureMessageConverters(...)` sai cách, có thể thay toàn bộ default converters thay vì chỉ mở rộng, khiến JSON route bị lỗi. Thường dùng `extendMessageConverters` hoặc Boot Jackson customizers khi chỉ cần điều chỉnh nhỏ. Sau khi thay converter, test **cả hai** request/response styles.

### Generic types

Với functional handlers, nếu cần deserialize JSON array của DTOs:

```java
List<NewNote> notes = request.body(
    new ParameterizedTypeReference<List<NewNote>>() {});
```

Đây là snippet với import `org.springframework.core.ParameterizedTypeReference` và `java.util.List`. Generic type token cho converter biết element type, thay vì `List.class` (có thể sinh Maps thay DTO). Bảo đảm converter hỗ trợ media type và body content.

## 8. Validation: tái sử dụng Validator, không kỳ vọng @Valid tự chạy

DTO record:

```java
public record NewNote(
        @NotBlank
        @Size(max = 80)
        String title) {}
```

Annotated method:

```java
public ResponseEntity<Note> create(
        @Valid @RequestBody NewNote input) {
    // Spring MVC kích hoạt Bean Validation theo annotated pipeline
}
```

Functional handler:

```java
NewNote input = request.body(NewNote.class);
Set<ConstraintViolation<NewNote>> violations =
        validator.validate(input);

if (!violations.isEmpty()) {
    return ServerResponse.badRequest()
            .body(new ApiError("invalid_note"));
}
```

**Sự khác biệt nằm ở bước kích hoạt validation**. Cùng Jakarta Validator Bean có thể được inject qua constructor, nhưng `HandlerFunction.handle(ServerRequest)` không có `@Valid @RequestBody` method argument để Spring tự xử lý giống annotated handler. Nếu dùng functional, hãy viết một helper nhất quán để:

1. Đọc JSON body và nhận biết malformed body.
2. Kiểm tra Bean Validation constraints.
3. Chuyển các violations thành error code/schema ổn định.
4. Không lộ exception stack trace hoặc giá trị nhạy cảm.
5. Phân biệt 400 (bad request) với 403 (not authorized), 404 (not found), 409 (conflict), 500 (server fault).

Với form binding, multipart, request params hoặc constructor binding phức tạp, annotated controller thường có auto binding features phong phú hơn; functional handler phải được thiết kế tường minh khi cần những API đó.

## 9. Error handling: nhất quán contract nhưng không đồng nhất pipeline

Một annotated endpoint có thể ném `MethodArgumentNotValidException` khi `@Valid` fail. Functional endpoint có thể tự trả `ServerResponse.badRequest().body(new ApiError(...))` hoặc bắt conversion exceptions đúng loại. Cả hai có thể trả HTTP 400 nhưng **body format khác nhau**.

Các điểm cần kiểm tra:

| Lỗi | Annotated MVC thông thường | Functional MVC cần chủ động kiểm thử |
| --- | --- | --- |
| JSON không hợp lệ | Resolver/converter có thể ném `HttpMessageNotReadableException` | `request.body(...)` có thể ném trong HandlerFunction |
| DTO vi phạm @NotBlank | `@Valid` method argument pipeline | Explicit Validator hoặc custom binding |
| `id=abc` khi cần long | MVC type conversion exception | `Long.parseLong`/conversion do handler gọi |
| Thiếu query param bắt buộc | `@RequestParam(required=true)` | `request.param(...)` Optional rồi validate |
| Unsupported media type | `consumes` mapping/converter | `contentType` predicate và converter; status có thể khác |
| Business conflict | Service exception/response | Cùng service; adapter mapping cần tương thích |
| Security rejection | Spring Security filter chain | Vẫn Spring Security filter chain, không bypass |
| Lỗi serialization | MVC return-value handling | `ServerResponse` body writing; test behavior |

### @ControllerAdvice có tự xử lý mọi functional error không?

**Không giả định.** Một số exception resolvers có thể xử lý exceptions trong cả hai flows, nhưng `@ExceptionHandler` thường gắn với khái niệm `HandlerMethod` của annotated controllers. Functional handlers có thể không đi đúng đường annotation-based error resolution. Hãy:

- Dùng **router-level `onError`/filter** theo API phù hợp phiên bản khi muốn error policy cho functional routes.
- Dùng explicit error-to-`ServerResponse` helpers cho conversion/validation do handler quản lý.
- Xác nhận global `HandlerExceptionResolver` và `ProblemDetail` response qua MockMvc.
- Không bắt `Exception` rồi luôn trả 400, vì sẽ che 500 thật.
- Nếu backend đã có chuẩn RFC 9457 Problem Details, test trường `type`, `title`, `status`, `detail` cho cả hai styles, thay vì chỉ kiểm tra HTTP status.

### Functional error boundary là một lớp khác controller advice

Một middleware/router filter có thể chọn short-circuit hoặc chặn exceptions:

```java
.filter((request, next) -> {
    try {
        return next.handle(request);
    } catch (IllegalArgumentException ex) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ApiError("bad_parameter"));
    }
})
```

Snippet này chỉ minh họa; chỉ bắt `IllegalArgumentException` **nếu** domain policy coi loại exception đó là bad input. Không nên dùng kiểu exception quá rộng cho nhiều lỗi khác bản chất. Lưu ý lỗi body serialization có thể xảy ra **sau** khi handler tạo `ServerResponse` nên filter bọc `next.handle()` không nhất thiết bắt được lỗi xảy ra khi body được ghi.

## 10. MVC Interceptor, Servlet Filter, functional filter, Security

Có ít nhất ba loại interception mà tên gọi dễ gây nhầm.

| Tầng | Ví dụ API | Phạm vi |
| --- | --- | --- |
| Servlet filter | `jakarta.servlet.Filter`, Spring `OncePerRequestFilter` | Trước DispatcherServlet, phụ thuộc URL/dispatcher mappings |
| MVC interceptor | `HandlerInterceptor` + `WebMvcConfigurer.addInterceptors` | MVC HandlerMappings được cấu hình để dùng interceptor |
| Functional filter | `RouterFunctions.Builder.filter` | Chỉ routes được RouterFunction builder/nhóm tương ứng tạo |
| Spring Security | `SecurityFilterChain` ở Servlet filters | Bảo vệ các HTTP requests theo security matcher rules |

### 10.1. Dùng chung MVC interceptor

Một ứng dụng đã có MVC correlation header, locale hoặc metrics interceptor có thể tiếp tục đăng ký:

```java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(new HandlerInterceptor() {
        @Override
        public boolean preHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler) {
            response.setHeader("X-MVC-Pipeline", "active");
            return true;
        }
    }).addPathPatterns("/api/**");
}
```

Đây là snippet để minh họa; class runnable ở mục 11. Tác dụng thực tế cần kiểm tra với các HandlerMapping được dùng trong phiên bản Spring/Boot đang chạy, đặc biệt nếu application tự đăng ký custom HandlerMappings. Spring MVC Java configuration thường cung cấp interceptors cho các mappings do nó quản lý.

**Lưu ý quan trọng:** Interceptors không phải nơi tối ưu để triển khai authorization vì có thể có khác biệt/mismatch giữa mappings; Spring docs khuyên dùng Spring Security hoặc Servlet filter chain cho bảo mật. Correlation/observability thích hợp hơn nhưng vẫn cần xử lý ASYNC redispatch khi có async endpoints.

### 10.2. Functional filter chỉ bọc functional routes

Ví dụ:

```java
RouterFunction<ServerResponse> router = route()
        .GET("/api/fn/notes", handler::list)
        .filter((request, next) -> {
            if ("true".equals(
                    request.headers().firstHeader("X-Demo-Block"))) {
                return ServerResponse.status(HttpStatus.FORBIDDEN)
                        .body(new ApiError("demo_blocked"));
            }
            return next.handle(request);
        })
        .build();
```

Snippet mang tính giáo dục, **không dùng header `X-Demo-Block` làm hệ thống authorization**. Khi request đi tới annotated URL, functional filter này không tự động chạy vì request không được RouterFunction đó handle. Ngược lại, Servlet Security filter chain áp dụng theo SecurityFilterChain matcher của toàn app.

### 10.3. Security FilterChain cho cả hai phong cách

Nếu ứng dụng có Spring Security:

- Request `/api/fn/**` và `/api/annotated/**` cần cùng hoặc tương đương security matcher policies.
- Filter chain xử lý authentication, authorization, CSRF, CORS integration và exception entry points **trước DispatcherServlet**.
- `@PreAuthorize` trên shared service methods có thể bảo vệ business layer nếu đã bật method security và invocation đi qua proxy; không chỉ dựa vào route matchers.
- Nếu dùng session/cookie auth, POST functional vẫn chịu CSRF protection khi policy bật. Không tắt CSRF vì functional route không dùng `@PostMapping`.
- Nếu phân quyền theo tenant/resource, phải kiểm tra quyền tại service sau khi biết resource ID, không chỉ kiểm tra URL prefix.
- Các functional filters để audit/transform không thay filter chain security chuẩn.

**Mô hình bảo mật:** Handler thích hợp có thể thay đổi theo routing style, nhưng danh tính user và quyền truy cập phải được kiểm tra nhất quán ở request và service boundaries.

## 11. Dự án Maven runnable: functional + annotated + shared MVC infrastructure

Demo sau chạy **một Spring Boot MVC application** với:

1. `POST /api/fn/notes`, `GET /api/fn/notes`, `GET /api/fn/notes/{id}`, `GET /api/fn/notes/latest` và `GET /api/fn/notes/search?q=...`.
2. Annotated equivalents tại `/api/annotated/notes`.
3. Một `NoteStore` singleton lưu dữ liệu trong RAM dùng chung, không tạo hai databases.
4. Cùng DTO và Jakarta Bean Validation.
5. Một MVC `HandlerInterceptor` ghi header `X-MVC-Pipeline: active` cho API routes.
6. Một `WebMvcConfigurer.addCorsMappings` minh họa global CORS.
7. Một functional filter giả lập `X-Demo-Block: true` để quan sát phạm vi route-specific filter.
8. MockMvc tests xác nhận HTTP status, Location, JSON, validations, shared store, routing và MVC interceptor.

**Giới hạn demo:** Không có Spring Security dependency, DB hay production authorization; `X-Demo-Block` chỉ là minh họa. CORS origin `https://portal.example.test` chỉ là tên minh họa; không phải một dịch vụ đang hoạt động.

### 11.1. Cấu trúc tệp

```text
mvc-mixed-endpoints/
├── pom.xml
└── src/
    ├── main/java/demo/mixed/
    │   ├── MixedApplication.java
    │   ├── Note.java
    │   ├── NewNote.java
    │   ├── ApiError.java
    │   ├── NoteStore.java
    │   ├── NoteHandler.java
    │   ├── FunctionalRoutes.java
    │   ├── AnnotatedNotesController.java
    │   └── MvcInfrastructureConfig.java
    └── test/java/demo/mixed/
        └── MixedMvcTest.java
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
    <groupId>demo</groupId>
    <artifactId>mvc-mixed-endpoints</artifactId>
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

### 11.2. Boot application

**`src/main/java/demo/mixed/MixedApplication.java`**

```java
package demo.mixed;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MixedApplication {
    public static void main(String[] args) {
        SpringApplication.run(MixedApplication.class, args);
    }
}
```

### 11.3. DTOs và entity đơn giản dùng chung

**`src/main/java/demo/mixed/Note.java`**

```java
package demo.mixed;

public record Note(long id, String title) {}
```

**`src/main/java/demo/mixed/NewNote.java`**

```java
package demo.mixed;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NewNote(
        @NotBlank @Size(max = 80) String title) {}
```

**`src/main/java/demo/mixed/ApiError.java`**

```java
package demo.mixed;

public record ApiError(String code) {}
```

Tất cả dùng Java 17 record. Jackson có thể serialize/deserialize các record này trong Spring Boot 3.3.5. `@NotBlank` và `@Size` chỉ đặt metadata constraints; chúng cần được validate qua `@Valid` (annotated method) hoặc `Validator.validate` (functional handler).

### 11.4. Shared business component

**`src/main/java/demo/mixed/NoteStore.java`**

```java
package demo.mixed;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class NoteStore {

    private final AtomicLong ids = new AtomicLong();
    private final ConcurrentHashMap<Long, Note> notes =
            new ConcurrentHashMap<>();

    public Note create(String title) {
        Note note = new Note(ids.incrementAndGet(), title.strip());
        notes.put(note.id(), note);
        return note;
    }

    public Optional<Note> find(long id) {
        return Optional.ofNullable(notes.get(id));
    }

    public List<Note> list() {
        List<Note> data = new ArrayList<>(notes.values());
        data.sort(Comparator.comparingLong(Note::id));
        return data;
    }

    public Optional<Note> latest() {
        return list().stream()
                .max(Comparator.comparingLong(Note::id));
    }

    public List<Note> search(String q) {
        String term = q.toLowerCase(Locale.ROOT).strip();
        return list().stream()
                .filter(n -> n.title()
                        .toLowerCase(Locale.ROOT).contains(term))
                .toList();
    }
}
```

Store chỉ là ví dụ: dữ liệu biến mất sau restart; không có persistence/authorization. Sự hiện diện của `ConcurrentHashMap` không giải quyết được transactions, tenant isolation hay unique constraints. Với DB thật, thay bằng service/repository/JPA và đặt `@Transactional` trên service method cần transaction. Functional lẫn annotated đều gọi cùng Spring proxy nếu injection đúng, nên không phải hai business implementations riêng.

### 11.5. Functional handler: ServerRequest/ServerResponse

**`src/main/java/demo/mixed/NoteHandler.java`**

```java
package demo.mixed;

import java.net.URI;

import jakarta.validation.Validator;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class NoteHandler {

    private final NoteStore store;
    private final Validator validator;

    public NoteHandler(NoteStore store, Validator validator) {
        this.store = store;
        this.validator = validator;
    }

    public ServerResponse list(ServerRequest request) throws Exception {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.list());
    }

    public ServerResponse latest(ServerRequest request) throws Exception {
        Note note = store.latest().orElse(null);
        if (note == null) {
            return ServerResponse.notFound().build();
        }
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }

    public ServerResponse search(ServerRequest request) throws Exception {
        String q = request.param("q").orElse("");
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.search(q));
    }

    public ServerResponse find(ServerRequest request) throws Exception {
        long id;
        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException ex) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError("bad_id"));
        }

        Note note = store.find(id).orElse(null);
        if (note == null) {
            return ServerResponse.notFound().build();
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }

    public ServerResponse create(ServerRequest request) throws Exception {
        NewNote input = request.body(NewNote.class);

        if (input == null || !validator.validate(input).isEmpty()) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError("invalid_note"));
        }

        Note note = store.create(input.title());
        URI location = URI.create("/api/fn/notes/" + note.id());

        return ServerResponse.created(location)
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }
}
```

**Điểm cần quan sát:**

- `@Component` để inject handler và reuse `NoteStore`/`Validator`.
- Không có `@RequestMapping`/`@PostMapping` trên class: functional `RouterFunction` chịu trách nhiệm mapping.
- `request.body(NewNote.class)` đọc JSON bằng MVC converter, sau đó handler chủ động gọi validator.
- `request.pathVariable("id")` được chuyển String sang long thủ công; nếu không hợp lệ trả JSON error `bad_id`.
- `ServerResponse.created(location)` trả **HTTP 201 Created** và `Location`; URI tương đối được xây từ prefix do server kiểm soát. Không lấy Host/Forwarded user-supplied rồi ghép redirect.
- Handler không giữ request-specific state trong object fields; `NoteStore` đồng thời được hai handler styles sử dụng.
- Trong production, `request.body(...)` có thể ném khi JSON malformed; demo không định nghĩa custom malformed JSON error schema. Test thực trước khi hứa một định dạng lỗi cụ thể.

### 11.6. RouterFunction bean

**`src/main/java/demo/mixed/FunctionalRoutes.java`**

```java
package demo.mixed;

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
    RouterFunction<ServerResponse> noteRoutes(NoteHandler handler) {
        return route()
                // Literal routes trước variable route.
                .GET("/api/fn/notes/latest", handler::latest)
                .GET("/api/fn/notes/search", handler::search)
                .GET("/api/fn/notes/{id}", handler::find)
                .GET("/api/fn/notes", handler::list)
                .POST("/api/fn/notes",
                        contentType(MediaType.APPLICATION_JSON),
                        handler::create)
                .filter((request, next) -> {
                    // Chỉ minh họa scope, KHÔNG phải authorization.
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

Cả `latest` và `search` nằm trước `/{id}`, tránh bị parse thành ID. `contentType(JSON)` áp cho POST body; nó không phải `accept(JSON)` (kiểm tra kiểu response client muốn nhận). Functional filter chỉ có hiệu lực trong router bean này, không áp lên annotated endpoint dưới `/api/annotated/**`.

Khi API có hàng chục routes, dùng `path(...)`/`nest(...)` hoặc multiple router beans để nhóm domain. Không dùng một wildcard functional route `/**` bắt toàn bộ và vô tình che static files, controllers hoặc error handlers.

### 11.7. Annotated controller dùng chung store

**`src/main/java/demo/mixed/AnnotatedNotesController.java`**

```java
package demo.mixed;

import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/annotated/notes")
public class AnnotatedNotesController {

    private final NoteStore store;

    public AnnotatedNotesController(NoteStore store) {
        this.store = store;
    }

    @GetMapping
    public List<Note> list() {
        return store.list();
    }

    @GetMapping("/latest")
    public ResponseEntity<Note> latest() {
        return store.latest()
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/search")
    public List<Note> search(@RequestParam(defaultValue = "") String q) {
        return store.search(q);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Note> find(@PathVariable long id) {
        return store.find(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Note> create(
            @Valid @RequestBody NewNote input) {
        Note note = store.create(input.title());
        URI location = URI.create(
                "/api/annotated/notes/" + note.id());
        return ResponseEntity.created(location).body(note);
    }
}
```

Annotated code cần ít HTTP plumbing hơn khi binding/validation đơn giản:
- `@PathVariable long id`: Spring MVC tự convert.
- `@RequestParam(defaultValue = "")`: Spring MVC tự đọc query/default.
- `@Valid @RequestBody`: dùng body converter + automatic Bean Validation.
- `ResponseEntity.created(location)`: trả 201 + Location.

Cùng `NoteStore` nghĩa note tạo qua `/api/fn/notes` có thể đọc qua `/api/annotated/notes/{id}` và ngược lại. Điều này chứng minh **coexistence trong chung business layer** chứ không chỉ hai response tĩnh.

### 11.8. WebMvcConfigurer: interceptor và CORS chung

**`src/main/java/demo/mixed/MvcInfrastructureConfig.java`**

```java
package demo.mixed;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcInfrastructureConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            @Override
            public boolean preHandle(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler) {
                response.setHeader("X-MVC-Pipeline", "active");
                return true;
            }
        }).addPathPatterns("/api/**");
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://portal.example.test")
                .allowedMethods("GET", "POST", "OPTIONS")
                .allowedHeaders("Content-Type", "Authorization");
    }
}
```

Đây là cấu hình **bổ sung**, không tạo DispatcherServlet thứ hai. Interceptor gửi `X-MVC-Pipeline: active` cho các MVC handlers mà MVC configuration đã gắn interceptor theo path; test dưới đây kiểm tra cả functional và annotated endpoints.

CORS cho phép browser scripts tại `https://portal.example.test` gọi các API đường `/api/**` theo methods/headers đã cho, nếu handler mapping/CORS integration hỗ trợ đầy đủ. Đây không cho phép website không đáng tin đọc dữ liệu user; khi thêm cookie auth, cần policy allowed credentials, CSRF và Spring Security CORS integration cẩn thận.

**Không bật `allowedOrigins("*")` kết hợp credentials tùy tiện**. Và không dùng CORS thay authentication: curl hoặc non-browser clients vẫn gọi API được khi không có security controls.

## 12. Chạy ứng dụng, quan sát cùng DispatcherServlet

Tại thư mục `mvc-mixed-endpoints` chứa `pom.xml`, cài Java 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Hai lệnh chạy theo thứ tự. Nếu chỉ muốn chạy server mà chưa thử tests, có thể chạy `mvn spring-boot:run` riêng. Với Boot default, server nghe tại `http://localhost:8080`.

### 12.1. Tạo note bằng functional route

```bash
curl -i -X POST 'http://localhost:8080/api/fn/notes' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Spring MVC Functional"}'
```

Trên JVM mới, chưa có dữ liệu nào:

```http
HTTP/1.1 201
Location: /api/fn/notes/1
Content-Type: application/json
X-MVC-Pipeline: active

{"id":1,"title":"Spring MVC Functional"}
```

Status 201 và Location là giao thức HTTP thật; không tạo URL bằng JSON field rồi trả HTTP 200. URL tương đối tránh phụ thuộc Host header chưa được kiểm chứng. Header `X-MVC-Pipeline` là từ MVC interceptor, không phải functional router filter.

### 12.2. Đọc lại từ annotated controller

```bash
curl -i 'http://localhost:8080/api/annotated/notes/1'
```

Dự kiến 200 và JSON:

```json
{"id":1,"title":"Spring MVC Functional"}
```

Nếu thấy đúng note đó, chứng minh hai endpoint styles dùng chung `NoteStore`.

### 12.3. Tạo note qua annotation, đọc qua functional

```bash
curl -i -X POST 'http://localhost:8080/api/annotated/notes' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Spring MVC Annotation"}'

curl -i 'http://localhost:8080/api/fn/notes/2'
```

Dự kiến note ID 2 xuất hiện trong response functional nếu hai requests chạy tuần tự sau lần tạo đầu và không có request nào khác chen vào. ID có thể khác trong test/in-memory state khác; đừng hardcode ID trong automated tests.

### 12.4. Search, latest và precedence

```bash
curl -G -i 'http://localhost:8080/api/fn/notes/search' \
  --data-urlencode 'q=Functional'

curl -i 'http://localhost:8080/api/fn/notes/latest'
```

Search trả JSON array notes có title chứa "Functional". Latest trả note có ID lớn nhất. Nếu route `/{id}` bị đặt trước `/search` hoặc `/latest`, client có thể nhận 400 bad_id — đây là lỗi route precedence của functional builder.

### 12.5. Functional-only filter

```bash
curl -i 'http://localhost:8080/api/fn/notes' \
  -H 'X-Demo-Block: true'

curl -i 'http://localhost:8080/api/annotated/notes' \
  -H 'X-Demo-Block: true'
```

Request đầu dự kiến `403` với body:

```json
{"code":"demo_blocked"}
```

Request thứ hai vẫn được annotated handler trả 200; nó không nằm trong functional router filter. **Đây không phải một policy cho quyền truy cập**: client có thể tự sửa header, và mọi security thực tế phải được kiểm soát ở Spring Security/service.

### 12.6. Validation 400 ở cả hai nhưng body có thể khác

```bash
curl -i -X POST 'http://localhost:8080/api/fn/notes' \
  -H 'Content-Type: application/json' \
  -d '{"title":"   "}'

curl -i -X POST 'http://localhost:8080/api/annotated/notes' \
  -H 'Content-Type: application/json' \
  -d '{"title":"   "}'
```

Functional handler chủ động trả:

```http
HTTP/1.1 400
Content-Type: application/json

{"code":"invalid_note"}
```

Annotated handler có thể trả 400 nhờ `@Valid`, nhưng **body mặc định do Boot/MVC error handling quyết định**, không phải tự nhiên trùng với `ApiError("invalid_note")`. Nếu API client cần error body chung, thiết kế adapter/error contract rõ ràng và test cả hai.

## 13. MockMvc: contract tests cho hai handler styles và hạ tầng dùng chung

**`src/test/java/demo/mixed/MixedMvcTest.java`**

```java
package demo.mixed;

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
import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MixedMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void functionalCreateCanBeReadByAnnotatedController()
            throws Exception {
        MvcResult created = mvc.perform(post("/api/fn/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Cross Style One\"}"))
                .andExpect(status().isCreated())
                .andReturn();

        String location = created.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);
        assertTrue(location.matches("/api/fn/notes/[1-9][0-9]*"));

        String id = location.substring(location.lastIndexOf('/') + 1);
        mvc.perform(get("/api/annotated/notes/" + id))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.title").value("Cross Style One"));
    }

    @Test
    void annotatedCreateCanBeReadByFunctionalHandler()
            throws Exception {
        MvcResult created = mvc.perform(
                    post("/api/annotated/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Cross Style Two\"}"))
                .andExpect(status().isCreated())
                .andReturn();

        String location = created.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);
        String id = location.substring(location.lastIndexOf('/') + 1);

        mvc.perform(get("/api/fn/notes/" + id))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.title").value("Cross Style Two"));
    }

    @Test
    void mvcInterceptorAppliesToBothHandlerStyles()
            throws Exception {
        mvc.perform(get("/api/fn/notes"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                    "X-MVC-Pipeline", "active"));

        mvc.perform(get("/api/annotated/notes"))
           .andExpect(status().isOk())
           .andExpect(header().string(
                    "X-MVC-Pipeline", "active"));
    }

    @Test
    void functionalFilterDoesNotInterceptAnnotations()
            throws Exception {
        mvc.perform(get("/api/fn/notes")
                    .header("X-Demo-Block", "true"))
           .andExpect(status().isForbidden())
           .andExpect(jsonPath("$.code").value("demo_blocked"));

        mvc.perform(get("/api/annotated/notes")
                    .header("X-Demo-Block", "true"))
           .andExpect(status().isOk());
    }

    @Test
    void functionalValidationUsesInjectedValidator()
            throws Exception {
        mvc.perform(post("/api/fn/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"   \"}"))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.code").value("invalid_note"));
    }

    @Test
    void annotationValidationUsesMethodArgumentPipeline()
            throws Exception {
        mvc.perform(post("/api/annotated/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"   \"}"))
           .andExpect(status().isBadRequest());
    }

    @Test
    void literalRoutesOutrankVariableRouteByDeclaredOrder()
            throws Exception {
        mvc.perform(post("/api/fn/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Latest Marker\"}"))
           .andExpect(status().isCreated());

        mvc.perform(get("/api/fn/notes/latest"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.id").isNumber());
    }

    @Test
    void searchReadsQueryParameter() throws Exception {
        mvc.perform(post("/api/fn/notes")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Unique Search Phrase\"}"))
           .andExpect(status().isCreated());

        mvc.perform(get("/api/fn/notes/search")
                    .param("q", "Unique Search Phrase"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$[0].title")
                    .value("Unique Search Phrase"));
    }

    @Test
    void missingResourceGets404InBothStyles()
            throws Exception {
        mvc.perform(get("/api/fn/notes/999999999"))
           .andExpect(status().isNotFound());

        mvc.perform(get("/api/annotated/notes/999999999"))
           .andExpect(status().isNotFound());
    }

    @Test
    void badFunctionalIdHasExplicitErrorContract()
            throws Exception {
        mvc.perform(get("/api/fn/notes/not-a-number"))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.code").value("bad_id"));
    }
}
```

Bộ test trên có **10 test methods**. Chạy:

```bash
mvn test
```

Khi source files được tạo đúng và tất cả tests pass, Maven exit code 0 với summary tương tự `Tests run: 10, Failures: 0, Errors: 0, Skipped: 0`. Đây là ví dụ được viết và rà soát tĩnh theo Java 17/Spring MVC 6.1; **chưa chạy Maven thực tế trong môi trường biên soạn bài trên Google Sheets**.

### Vì sao test không hardcode ID 1/2?

Tests dùng `NoteStore` chung trong cùng application context; thứ tự chạy JUnit tests không phải contract. Sau khi POST, đọc `Location` thực và lấy ID từ URI rồi thực hiện GET. Như vậy tests ít phụ thuộc thứ tự/parallel test state hơn. Với production DB, còn phải tính isolation/test transaction/cleanup theo từng test.

### MockMvc kiểm chứng được gì và còn thiếu gì?

MockMvc kiểm chứng:
- DispatcherServlet routing tới đúng functional hoặc annotated handler.
- Header từ MVC interceptor.
- Functional router filter không áp annotated endpoint.
- JSON converter, validation/status và `Location`.
- Shared store/read-your-write behavior.
- Literal route không bị `/{id}` bắt nhầm.

MockMvc **không đủ** để chứng minh:
- Reverse proxy rewrite Host/Forwarded/CORS đúng trên deployment thật.
- Servlet security chain hoạt động theo cấu hình production nếu test không thêm Spring Security.
- HTTP client abort/async timeout/socket backpressure.
- DB transaction rollback, deadlocks, connection pooling dưới concurrency.
- OpenAPI generator phát hiện functional routes.
- Cache/CDN policy không leak dữ liệu user.

Bổ sung integration tests qua embedded server/gateway và Spring Security test support khi ứng dụng thật có những chức năng đó.

## 14. CORS và preflight: cấu hình phải đi qua đúng mapping

Một browser gửi request từ `https://portal.example.test` tới `http://localhost:8080/api/fn/notes` sẽ bị same-origin policy kiểm soát. CORS là cơ chế cho **browser** quyết định đọc cross-origin response; nó không chứng minh user đã authenticated hay authorized.

Với `WebMvcConfigurer.addCorsMappings("/api/**")`, MVC HandlerMappings có thể dùng policy đã đăng ký. Tuy nhiên preflight `OPTIONS` được xử lý ở mapping/CORS processing layer; `RouterFunction` với các predicates GET/POST có thể tạo nhánh error khác nếu cấu hình/routing/custom filters khác nhau. Khi thêm functional endpoints vào ứng dụng cũ, **phải test preflight** thực:

```bash
curl -i -X OPTIONS \
  'http://localhost:8080/api/fn/notes' \
  -H 'Origin: https://portal.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

Quan sát `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` và status. Không giả định header `@CrossOrigin` trên một annotated controller sẽ tự áp dụng cho một functional endpoint khác.

Khi có Spring Security, nên tích hợp CORS ở security filter chain phù hợp, vì preflight thường không chứa session cookie; nếu security chặn trước CORS processor thì browser request có thể thất bại. Chỉ bật `allowCredentials(true)` với origins đáng tin và không phối hợp wildcard origins không hợp lệ.

## 15. Multipart, file upload, static resources và templates

Khi dần chuyển sang functional endpoints, không phải mọi use case đều có một bản chuyển đổi 1:1 đơn giản.

### Multipart / forms

Annotated MVC cho phép:

```java
@PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> upload(
        @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    // ...
}
```

Snippet trên có types chưa định nghĩa. Đây là use case Spring binding tự hỗ trợ đa dạng. Với WebMvc.fn có thể truy cập `ServerRequest.servletRequest()` / multipart servlet facilities và dùng converters/helpers phù hợp, nhưng **không giả định** có cùng `@RequestPart` method argument auto-resolution trong một HandlerFunction. Nếu API có nhiều uploads/validation constraints/binding, giữ annotated controller có thể đơn giản và dễ bảo trì hơn.

### Static resources

Spring MVC thường phục vụ JS/CSS/images từ `classpath:/static` qua resource handler và cache policy. WebMvc.fn có `RouterFunctions.resources(...)`/`resource(...)` cho cases đặc biệt; không cần thay static resource handler chỉ để thống nhất phong cách functional.

Nếu viết SPA fallback route như `/**`, đảm bảo không che:
- `/api/**` handlers và 404.
- Actuator/health endpoints.
- Static resources/assets caching và range requests.
- Security-sensitive paths.

Với một URL không khớp functional route, RouterFunction có thể trả empty, để DispatcherServlet kiểm tra HandlerMappings khác. Nhưng một catch-all functional route có thể match quá sớm và làm mất fallback theo ý định.

### Rendering templates

Annotated `@Controller` có `Model`, `@ModelAttribute` và view name. WebMvc.fn cũng có cơ chế render views qua `ServerResponse`/view resolvers ở MVC, nhưng không có automatic method argument binding của controller annotations. Nếu dự án lớn dùng Thymeleaf forms, custom binders và validation message codes, phải đánh giá chi phí chuyển đổi; giữ annotated MVC cho web pages và WebMvc.fn cho API modules có thể là cách kết hợp hợp lý.

## 16. Observable application: logs, metrics, tracing và interceptors

Trước khi thêm một routing model, team nên biết tracing/metrics đang dựa trên lớp nào.

1. **Servlet Filter / Spring Security filter**: có thể quan sát cả functional và annotated requests theo URL pattern.
2. **MVC interceptor**: thường bao phủ các HandlerMappings MVC do cấu hình quản lý, nhưng có thể phụ thuộc dispatch type, exception/async lifecycle.
3. **HandlerMethod-specific instrumentations**: có thể cần thêm support cho `HandlerFunction`; không giả định tên controller/method là metrics tags cho functional endpoints.
4. **Micrometer/Observations**: frameworks có integration HTTP server chung, nhưng naming/tagging của route patterns cần kiểm chứng ở version được deploy.
5. **Structured logging/MDC**: đường route nào cũng cần trace ID, tránh log secret body/Authorization; async workers cần propagation nếu có.

Một cách kiểm tra đơn giản là gửi cùng loại GET tới `/api/fn/notes` và `/api/annotated/notes`, rồi so sánh:
- Trace/span ID có xuất hiện đầy đủ?
- HTTP method/status/route pattern tags có nhất quán?
- Request latency/error counts có được tính cho cả hai?
- Security principal/tenant correlation có đúng?
- Exception được ghi nhận là 4xx hay 5xx?
- Không tạo hai spans trùng khi Servlet async redispatch?

Đây là phần quan trọng khi migration: API có thể trả HTTP đúng nhưng **mất giám sát** nếu instrumentation chỉ bắt `HandlerMethod`.

## 17. Versioning và contract tests khi chuyển dần

Một dự án cũ có `/api/v1/orders` được annotated controller phục vụ. Nếu chuyển từng route sang functional, có thể tách theo HTTP operation hoặc resource subdomain:

```text
Trước migration:
  GET  /api/v1/orders        @RestController
  POST /api/v1/orders        @RestController
  GET  /api/v1/orders/{id}   @RestController

Giai đoạn chuyển:
  GET  /api/v1/orders        @RestController
  POST /api/v1/orders        WebMvc.fn
  GET  /api/v1/orders/{id}   @RestController

Sau migration nếu cần:
  GET  /api/v1/orders        WebMvc.fn
  POST /api/v1/orders        WebMvc.fn
  GET  /api/v1/orders/{id}   WebMvc.fn
```

**Điều kiện:** một method + route chỉ có **một** owner trong từng release; không khai báo duplicate và hy vọng HandlerMapping order tự xử lý migration. Cập nhật controller/router theo commit/release có tests; không thay URL contract với clients một cách vô tình.

### Contract checklist

Với mỗi endpoint, so sánh trước/sau:
- Method/path/trailing slash và status 200/201/204/400/404/405/406/415.
- Header `Content-Type`, `Location`, `Cache-Control`, `ETag`, `Vary`, CORS và security headers.
- JSON field names, null handling, ordering (nếu contract yêu cầu), locale/timezone.
- Validation constraints/error body/schema.
- Cookie/session/CSRF/authorization behavior.
- Pageable/sorting/query param semantics, duplicate query values.
- Multipart and file download: content type, bytes, range requests.
- Compression/proxy/forwarded host and context paths.
- OpenAPI docs + generated clients, operation IDs và required fields.
- Trace/metrics, load/timeout và rate limiting.

**Không đo “thành công” chỉ bằng việc controller không còn @GetMapping.** Migration thành công khi API consumers không bị phá hợp đồng và hạ tầng quan sát/bảo mật không suy giảm.

## 18. Các chiến lược xử lý lỗi cho một ứng dụng hỗn hợp

Mục tiêu là một response schema thống nhất, ví dụ:

```json
{
  "code": "invalid_note",
  "message": "Title must not be blank"
}
```

Nhưng không cần ép cả hai handler styles đi qua **cùng exception class**. Một cách tổ chức:

1. Định nghĩa `ApiError` hoặc `ProblemDetail` contract ở module HTTP-shared.
2. Có adapter cho annotated exceptions (`MethodArgumentNotValidException`, type mismatch, message-not-readable) và adapter cho functional exceptions/body validation.
3. Mọi branch trả status phù hợp; đừng vô tình biến business 409 thành 500 hoặc 400.
4. Ghi log với trace ID, không leak raw rejected PII/secrets.
5. Tests gửi cùng invalid requests tới cả endpoints và so sánh status + stable error fields.
6. Kiểm thử cả errors ở converter/write phase vì không phải mọi exception xảy ra trong handler lambda.
7. Khi đã trả một phần streaming response, status/body không còn sửa tùy ý.
8. Với handler exception resolutions, phân biệt hạ tầng global với `@ControllerAdvice` hướng method annotations.

### Vì sao không bắt Exception rộng trong mọi functional filter?

```java
// PHẢN VÍ DỤ: che mọi bug thành bad request.
try {
    return next.handle(request);
} catch (Exception e) {
    return ServerResponse.badRequest().body("invalid");
}
```

Lỗi database, NullPointerException, permission checks hoặc network failures có thể bị phân loại sai, che sự cố và làm monitoring/circuit breaker không hiệu quả. Chỉ bắt exception mà application có thể giải thích đúng ngữ nghĩa, còn những lỗi ngoài dự kiến để error boundary chung ghi nhận 5xx.

## 19. Hiệu năng: functional style không phải non-blocking I/O

Một functional handler:

```java
return ServerResponse.ok().body(
        blockingRepository.findAll());
```

vẫn có thể block Servlet request thread khi `findAll()` chạy JDBC đồng bộ. Trong cùng MVC Servlet stack, thay `@GetMapping` bằng lambda/RouterFunction không biến database/HTTP client thành reactive/non-blocking.

Nếu ứng dụng gặp bottleneck do I/O:
- Đo DB pool, remote latency và thread saturation trước.
- Cân nhắc pooling, caching, queries/index và timeouts.
- Với MVC, `Callable`/`DeferredResult` có thể giải phóng initial Servlet thread, nhưng blocking work có thể chuyển sang worker executor.
- Với streaming/live events, đánh giá backpressure và connection limits.
- Chỉ cân nhắc WebFlux khi data path phù hợp reactive/non-blocking và team có lý do về concurrency/resource usage; không dùng WebFlux chỉ để có functional router syntax.

Một migration WebMvc.fn hữu ích về **cấu trúc code** cũng có thể giữ nguyên throughput. Vì vậy benchmark dựa trên workload, không dựa vào từ "functional".

## 20. Những lỗi thường gặp khi tích hợp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Functional endpoint trả 404 | RouterFunction bean không scan, import WebFlux package, predicate không match | Kiểm tra application context, package và request method/path |
| Annotated API bị mất sau khi thêm router | Catch-all functional route hoặc custom MVC config | Tránh `/**`/overlap, không bật `@EnableWebMvc` tùy tiện |
| Route /latest bị parse thành ID | `/{id}` đặt trước literal route | Đặt literal routes đầu, test precedence |
| Có hai implementations cùng URL | Hai HandlerMappings cùng có match | Phân một owner cho mỗi method/path, chuyển theo release |
| JSON đọc được bên annotated nhưng functional fail | `request.body(...)`/contentType predicate khác annotation pipeline | Dùng đúng converters/media type, test malformed JSON |
| `@NotBlank` không báo 400 bên functional | Chưa gọi Validator | Inject `Validator` và validate explicit |
| Error body khác dù cùng 400 | Annotated advice khác functional explicit responses | Shared API error contract + tests |
| `@ControllerAdvice` không bắt functional exception | Handler không phải HandlerMethod | Functional error boundary hoặc global resolver phù hợp |
| Functional filter không chạy trên annotation | Router-level scope | Sử dụng Servlet filter / Spring Security cho concerns toàn app |
| MVC interceptor không chạy ở một custom mapping | HandlerMapping custom không được cấu hình tương ứng | Kiểm tra registry/MappedInterceptor và mapping order |
| CORS preflight bị 403 | Security/CORS order hoặc policy thiếu | Spring Security CORS integration và OPTIONS tests |
| POST functional bị CSRF 403 | Cookie/session auth vẫn có CSRF policy | Gửi CSRF token hợp lệ, không tắt tùy tiện |
| OpenAPI thiếu route | Tool không tự discover RouterFunction đầy đủ | Chọn compatible integration hoặc explicit docs |
| Trace/meter thiếu handler tag | Metrics integration chỉ nhìn annotation metadata | Verify instrumentation cho functional handler |
| ResponseBodyAdvice không can thiệp | Functional response writing path khác annotated | Viết shared converter/HTTP adapter phù hợp, test |
| URL Location sai sau reverse proxy | Forwarded headers trust/path prefix sai | Trusted ingress, canonical base URL/relative URI |
| DTO overposting/IDOR | Validation chỉ kiểm tra cú pháp, không xác thực quyền | Server-owned identity và per-resource authorization |
| Static JS/css bị 404 | Catch-all route chặn resource handler | Đặt static routing/SPA fallback đúng scope |
| GET trả body khác nhau giữa hai styles | Jackson/view configuration hoặc adapter behavior khác | Contract tests cả fields, headers, bytes và nulls |
| Async request mất MDC/security context | Cross-thread context không tự propagate | Delegating executor/context propagation đúng |
| File upload không bind MultipartFile | Functional không có @RequestPart method args như annotated | Giữ annotated cho multipart hoặc viết binding explicit |

## 21. Checklist triển khai production

1. Xác định functional endpoints có thật sự đem lại lợi ích về route composition, testability, maintainability.
2. Không thêm một MVC Servlet application thứ hai; dùng RouterFunction bean trong context hiện hữu.
3. Sử dụng đúng namespace `org.springframework.web.servlet.function`.
4. Giữ annotated controllers cần thiết; không rewrite toàn app vô lý.
5. Tách REST adapter khỏi business layer, dùng lại Spring `@Service` và transaction boundaries.
6. Kiểm tra RouteFunctionMapping discovery/order, nhất là nếu nhiều router beans.
7. Tránh method/path ownership trùng nhau; đặt literal route trước path variable.
8. Tiếp tục dùng converter/JSON configuration chung; không vô tình override defaults.
9. Thực thi Bean Validation chủ động ở functional handlers.
10. Thiết kế error schema/chính sách status thống nhất cả hai pipelines.
11. Đặt Spring Security/CSRF/auth ở filter chain/service chứ không chỉ functional filter.
12. Test MVC interceptors và Servlet filters với functional + annotated routes.
13. Test CORS preflight, OPTIONS/HEAD và headers.
14. Kiểm tra static resource handling/SPA fallback để không che routes khác.
15. Bảo vệ Host/Forwarded headers và location redirects khi chạy sau proxy.
16. Verify OpenAPI docs và generated client contract sau migration.
17. Verify logging/tracing/metrics có đủ routes/status.
18. Không suy luận functional là non-blocking; kiểm tra database/network performance thật.
19. MockMvc contract tests trên mọi path; bổ sung integration tests cho proxy/security/database.
20. Roll out từng route có rollback strategy, theo dõi 4xx/5xx và latency.

## 22. Bài tập tự kiểm tra

1. Vì sao WebMvc.fn và @RestController có thể sống chung trong một Spring Boot Web application?
2. `RouterFunctionMapping` và `RequestMappingHandlerMapping` khác nhau ở vai trò gì?
3. Với `GET /api/fn/notes/latest`, vì sao `/{id}` có thể gây lỗi nếu đứng trước?
4. Một `NoteStore` singleton có thể được dùng bởi cả annotated và functional handlers không? Tại sao?
5. `ServerRequest.body(NewNote.class)` có tự động kích hoạt `@NotBlank` không?
6. Nếu một app có `@RestControllerAdvice` cho MethodArgumentNotValidException, có chắc mọi functional validation error đi qua advice đó không?
7. `WebMvcConfigurer.addInterceptors` khác `RouterFunctions.Builder.filter` về phạm vi ở đâu?
8. Functional filter gắn vào `/api/fn/**` có bảo vệ `/api/annotated/**` không?
9. Vì sao Spring Security filter chain vẫn phải áp dụng khi chuyển sang functional endpoints?
10. Một preflight request OPTIONS từ browser có thể bị chặn ở đâu trước khi tới functional handler?
11. `@Transactional` trong shared service có ý nghĩa thế nào đối với hai handler styles?
12. Có thể tránh duplicate route bằng cách viết một HandlerMapping với order nhỏ hơn không, hay nên có một owner rõ ràng?
13. Vì sao static fallback `/**` có thể gây ra các 404/200 sai cho API?
14. Khi mixed app trả 400 từ cả hai styles, client có chắc nhận cùng JSON error schema không?
15. Vì sao đổi syntax router không tự làm JDBC non-blocking?
16. Khi migrate một endpoint, những HTTP headers nào ngoài JSON body cần kiểm tra?
17. CORS có thay authentication/authorization được không?
18. Làm sao chứng minh interceptor dùng chung hoạt động: chỉ đọc config hay test HTTP thực?
19. Vì sao OpenAPI instrumentation có thể nhìn annotated endpoints dễ hơn functional routes?
20. Khi nào giữ annotated controller thay vì chuyển sang WebMvc.fn?

**Gợi ý:** (1) Cùng DispatcherServlet, khác HandlerMapping/Adapter. (2) Functional vs annotation routing. (3) First-match order. (4) Có, cùng Spring IoC context/business service. (5) Không; cần Validator explicit. (6) Không nên giả định. (7) MVC mapping config vs router-local handler composition. (8) Không. (9) Bảo vệ toàn HTTP request, không chỉ lambdas. (10) Servlet/Security filters hoặc CORS/HandlerMapping policy. (11) Transaction áp dụng tại service proxy, không phụ thuộc HTTP adapter. (12) Một route owner rõ ràng an toàn hơn. (13) Match quá rộng có thể che static/other mappings. (14) Không. (15) Framework vẫn chạy Servlet stack/blocking dependencies. (16) Status, Content-Type, Location, CORS, cache, security, ETag... (17) Không. (18) MockMvc/integration test cả hai paths. (19) Tooling đọc HandlerMethod/annotations. (20) Khi binding/form/validation/error tooling hiện hành phù hợp hơn, không có lợi ích migration rõ.

## 23. Tài liệu chính thức và đọc thêm

- [Spring Framework 6.1 — Functional Endpoints (Spring MVC)](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc-functional.html)
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html)
- [Spring Framework 6.1 — RouterFunctions Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/function/RouterFunctions.html)
- [Spring Framework 6.1 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/function/ServerRequest.html)
- [Spring Framework 6.1 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/function/ServerResponse.html)
- [Spring Framework 6.1 — RouterFunctionMapping Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/function/support/RouterFunctionMapping.html)
- [Spring Framework — MVC Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config.html)
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [Spring Framework — MVC Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html)
- [Spring Framework — Exception Handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring MVC Testing — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)

**Tổng kết:** Functional endpoints là một cách khai báo HTTP routes trong Spring MVC hiện hữu, **không phải một web server/framework khác**. `RouterFunction` + `HandlerFunction` có thể cùng chạy với annotated controllers trên `DispatcherServlet`; chúng dùng chung Spring IoC, service/repository, HTTP converters và nhiều cấu hình MVC. Nhưng annotation-specific argument binding/validation/error handling **không tự được sao chép sang functional handlers**. Để tích hợp an toàn, hãy giữ business logic dùng chung, phân rõ route ownership, thiết kế validation và error contracts tường minh, bảo vệ HTTP bằng Servlet/Spring Security, kiểm thử interceptors/CORS/OpenAPI và phát hành từng phần có regression tests.

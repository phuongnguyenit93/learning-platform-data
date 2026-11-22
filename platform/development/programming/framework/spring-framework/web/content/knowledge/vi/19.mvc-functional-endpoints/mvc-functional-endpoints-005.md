# HandlerFilterFunction, xử lý lỗi và tổ chức các tuyến chức năng trong Spring MVC

## 1. Bài toán: tránh lặp logic khi API có nhiều functional routes

Spring MVC không bắt buộc mỗi HTTP endpoint phải là một method gắn `@GetMapping` hay `@PostMapping`. Bên cạnh annotated controllers, Spring hỗ trợ **WebMvc.fn**, nơi route và handler là các hàm có hợp đồng rõ ràng:

- `RouterFunction<ServerResponse>` chọn handler phù hợp với request.
- `HandlerFunction<ServerResponse>` nhận `ServerRequest` và trả `ServerResponse`.
- `HandlerFilterFunction<ServerResponse, ServerResponse>` bao quanh lời gọi handler để xử lý những mối quan tâm chung như logging, đo thời gian, kiểm soát đầu vào hay một kiểu short-circuit theo nghiệp vụ.
- `RouterFunctions.Builder` cho phép nhóm routes theo prefix/path/predicate, thêm `before`/`after`/`filter` và khai báo `onError` theo phạm vi.

Khi API phát triển, ba vấn đề thường xuất hiện:

1. Mười route cùng cần log hoặc kiểm tra header, khiến code trong từng handler bị lặp.
2. Một exception nghiệp vụ phải được ánh xạ thành HTTP status/body giống nhau, nhưng handler nào cũng có `try/catch` riêng.
3. Routes cho các nhóm `/api/v1/notes`, `/api/v1/orders`, `/admin/**` được khai báo không theo thứ tự, gây route shadowing hoặc filter lan sang endpoint không liên quan.

Giải pháp không phải đặt mọi thứ trong một filter khổng lồ. Cần hiểu **phạm vi của router functions**, vị trí của từng filter và nơi xử lý exception.

**Baseline:** Java 17+, Spring Framework **6.2.x** / Spring Boot **3.5.x**, Spring MVC trên Servlet stack. Toàn bộ imports cho functional API thuộc **`org.springframework.web.servlet.function`**; **không** dùng `org.springframework.web.reactive.function.server` của WebFlux. Code mẫu dùng in-memory repository để tập trung vào tổ chức routes; không bao gồm database hay authentication production.

## 2. Luồng xử lý WebMvc.fn trong DispatcherServlet

Functional MVC không tạo một HTTP server độc lập với Spring MVC. Nó chạy trong hạ tầng Servlet/`DispatcherServlet`:

```text
HTTP Request
     |
     v
Servlet FilterChain
     |
     v
DispatcherServlet
     |
     v
HandlerMappings
  RouterFunctionMapping -> tìm RouterFunction matching
     |
     v
HandlerFunctionAdapter
     |
     v
HandlerFilterFunction(s)
  pre logic -> next.handle(request) -> post logic
     |
     v
HandlerFunction(ServerRequest) -> ServerResponse
     |
     v
HttpMessageConverter / Servlet response writer
     |
     v
HTTP status + headers + body
```

Nếu một `RouterFunction` không match, cơ chế routing trả **`Optional.empty()`** và DispatcherServlet có thể xét những mappings khác. Nếu có handler được chọn, các filters gắn với router đó mới có cơ hội thực thi.

Trong WebMvc.fn:

```java
@FunctionalInterface
interface HandlerFunction<T extends ServerResponse> {
    T handle(ServerRequest request) throws Exception;
}
```

Đây là **chữ ký khái niệm** của API Spring, không cần tự khai báo interface trong project. `ServerRequest` và `ServerResponse` dùng cách tiếp cận bất biến/immutable contract; bạn trả một response object do builder tạo, không trực tiếp viết toàn bộ Servlet output như code thấp tầng.

Ví dụ ngắn:

```java
RouterFunction<ServerResponse> router =
        RouterFunctions.route()
                .GET("/hello", request ->
                        ServerResponse.ok()
                                .contentType(MediaType.TEXT_PLAIN)
                                .body("Hello WebMvc.fn"))
                .build();
```

Đây là **fragment**, cần imports WebMvc.fn, `MediaType` và đăng ký thành bean `@Bean` nếu muốn DispatcherServlet tìm được. Nó chưa có filters/error handling, nhưng là điểm xuất phát.

## 3. `HandlerFilterFunction` thực sự nhận tham số gì?

Trong Spring MVC:

```java
import org.springframework.web.servlet.function.HandlerFilterFunction;
import org.springframework.web.servlet.function.HandlerFunction;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;
```

Hợp đồng phương thức chính:

```java
R filter(ServerRequest request, HandlerFunction<T> next)
        throws Exception;
```

Trong đó:

- `request` là functional request của route match.
- `next` đại diện **handler hoặc filter kế tiếp** trong chuỗi.
- `next.handle(request)` cho phép thực thi phần tiếp theo.
- `ServerResponse` trả về là response cuối cho xử lý route sau khi filters bao quanh.
- Filter có thể **không** gọi next và tự trả response, ví dụ chặn request thiếu header bắt buộc.
- Filter có thể dùng `try/finally` để cleanup context hoặc đo duration khi downstream ném exception.
- Filter có thể bắt **những exception đã xác định**, trả response khác hoặc chuyển exception cho `onError`/MVC exception resolvers xử lý.

### 3.1. Dạng cơ bản: trước → next → sau

```java
HandlerFilterFunction<ServerResponse, ServerResponse> timer =
        (request, next) -> {
            long started = System.nanoTime();
            try {
                return next.handle(request);
            } finally {
                long elapsedNanos = System.nanoTime() - started;
                // Record metric đã được chuẩn hóa.
            }
        };
```

Đây là **fragment**, không phải runnable class; chưa có metrics sink. `finally` quan trọng vì cleanup/recording vẫn chạy khi downstream ném exception.

Ví dụ minh họa một filter có thể trả lỗi sớm:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> requireDemoHeader =
        (request, next) -> {
            String value = request.headers()
                    .firstHeader("X-Demo-Client");
            if (!"learning".equals(value)) {
                return ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(new ApiError(
                                "DEMO_HEADER_REQUIRED",
                                "Missing demo client header"));
            }
            return next.handle(request);
        };
```

Fragment giả định có record `ApiError`. Header `X-Demo-Client` **chỉ là quy tắc mô phỏng cho bài học**, không được dùng như authentication. Client hoàn toàn có thể tự tạo header. Với API thật, authentication/authorization do **Spring Security `SecurityFilterChain`** xử lý, cộng với quyền trên tài nguyên.

### 3.2. Filter không phải Servlet Filter hay MVC HandlerInterceptor

| Cấp | API | Thời điểm/vùng tác dụng |
| --- | --- | --- |
| **Servlet container** | `jakarta.servlet.Filter` | Trước/bao quanh Servlet, có URL mapping + dispatcher types |
| **Spring Security** | `FilterChainProxy` / `SecurityFilterChain` | Cơ chế bảo vệ HTTP request, authentication, authorization, CSRF |
| **Spring MVC functional route** | `HandlerFilterFunction` | Sau khi một router function match; chỉ nằm trong phạm vi router được gắn |
| **Spring MVC annotated controller** | `HandlerInterceptor` | Trên handler được MVC chọn qua interceptor registrations |
| **Exception infrastructure** | `HandlerExceptionResolver`, `@ControllerAdvice` | Có các contract xử lý lỗi khác và thứ tự ưu tiên riêng |

Vì handler filter nằm **bên trong functional routing**, nó không tự chạy trên:

- Endpoint annotated `@RestController` không thuộc router function đó.
- Static resources do resource handler khác phục vụ.
- Servlet khác, filter chain trước `DispatcherServlet`.
- Request **không match** bất cứ route nào trong router đã gắn filter.
- Các request bị Spring Security từ chối **trước khi** vào handler.

**Không dùng `HandlerFilterFunction` thay cho Spring Security** trên những ranh giới bảo mật bắt buộc của toàn ứng dụng.

## 4. `RouterFunctions.route()`: builder và thứ tự routes

Tạo router với các routes HTTP:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/api/v1/notes", handler::list)
                .GET("/api/v1/notes/{id}", handler::get)
                .POST("/api/v1/notes", handler::create)
                .build();
```

Đây là fragment, giả định `handler` có các methods đúng kiểu `ServerRequest -> ServerResponse`.

### 4.1. Route đầu tiên khớp là route được chọn

**Quan trọng:** WebMvc.fn đánh giá `RouterFunction` **theo thứ tự khai báo**. Nếu một route khái quát match trước, route đặc hiệu phía sau có thể không bao giờ được chọn:

```java
// Dễ sai: route biến động có thể match "stats" trước.
RouterFunctions.route()
        .GET("/api/v1/notes/{id}", handler::get)
        .GET("/api/v1/notes/stats", handler::stats)
        .build();
```

Trong ví dụ trên, GET `/api/v1/notes/stats` có thể đi vào `get` với `id="stats"` rồi thất bại khi parse ID. Khai báo static route trước:

```java
RouterFunctions.route()
        .GET("/api/v1/notes/stats", handler::stats)
        .GET("/api/v1/notes/{id}", handler::get)
        .build();
```

Đây là khác biệt với annotated controller model, nơi framework có thuật toán chọn mapping đặc hiệu. **Đừng dựa vào heuristic “Spring sẽ tự chọn static path trước” trong WebMvc.fn**. Với overlapping predicates như `accept`, `contentType` hay nested wildcard, nguyên tắc first matching route vẫn cần được kiểm chứng bằng tests.

### 4.2. Route predicates và HTTP media types

`RequestPredicates` hỗ trợ điều kiện kết hợp:

```java
import static org.springframework.web.servlet.function.RequestPredicates.accept;
import static org.springframework.web.servlet.function.RequestPredicates.contentType;
```

Ví dụ:

```java
RouterFunctions.route()
        .GET("/notes", accept(MediaType.APPLICATION_JSON),
                handler::list)
        .POST("/notes", contentType(MediaType.APPLICATION_JSON),
                handler::create)
        .build();
```

Đây là fragment. `accept` xét thứ client có thể nhận trong response; `contentType` xét định dạng request body. Một request không match predicate có thể rơi qua routes khác hoặc nhận 404/405/406/415 tùy mappings/resolvers, **không** mặc định cứ sai Content-Type là mọi cấu hình trả 415.

Nếu yêu cầu API rõ ràng rằng POST chỉ nhận JSON, có thể dùng predicate và thêm error contract cho unsupported media types qua exception handling hoặc infrastructure. Handler vẫn phải validate nội dung đã deserialize.

## 5. Tổ chức routes bằng `path` và `nest`

Thay vì lặp `/api/v1` ở từng route, nhóm một prefix:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api/v1", api -> api
                        .GET("/notes/stats", handler::stats)
                        .GET("/notes/{id}", handler::get)
                        .GET("/notes", handler::list)
                        .POST("/notes", handler::create))
                .build();
```

`path("/api/v1", consumer)` tạo nested builder. Suffix route bên trong sẽ được ghép theo semantics của `RequestPredicate`. Dễ review hơn khi toàn bộ version API nằm trong cùng một group.

### 5.1. Nest theo predicate khác path

Ví dụ nhiều GET routes chỉ dành cho client nhận JSON:

```java
RouterFunctions.route()
        .path("/api/v1/notes", notes -> notes
                .nest(
                    RequestPredicates.accept(
                            MediaType.APPLICATION_JSON),
                    json -> json
                            .GET("/stats", handler::stats)
                            .GET("/{id}", handler::get)))
        .build();
```

Trong bài này, `nest` có ý nghĩa gom những routes dùng chung một predicate. Nó **không** tự thực thi validation nội dung JSON hay thêm Security. `accept` là điều kiện match trên Accept header; muốn giới hạn body JSON của POST, dùng `contentType` tương ứng.

### 5.2. Phạm vi filter theo nhóm

Xét hai routes:

```java
RouterFunctions.route()
        .GET("/health", healthHandler)
        .path("/api/v1", api -> api
                .GET("/notes", notesHandler)
                .filter(notesFilter))
        .build();
```

`notesFilter` thuộc nested builder `/api/v1`, **không** áp lên `GET /health`. Nếu thay vào đó gắn `.filter(notesFilter)` ở outer builder sau `path(...)`, filter có thể áp vào **cả /health và nhóm API**.

Tài liệu Spring nhấn mạnh filter thêm vào nested routes không chạy trên top-level routes. Điều này cho phép chia trách nhiệm:

- Shared API filter cho `/api/v1/**`.
- Narrow filter cho `/api/v1/admin/**`.
- Không yêu cầu auth/business header cho `/health`.
- Filter ở outer builder nếu thật sự phải áp tới toàn bộ routes đã xây.

Đừng giả định bất kỳ filter nào “tự áp toàn ứng dụng”. Kiểm tra chính xác builder/RouterFunction mà bạn gắn filter.

## 6. Ba cách thêm hành vi chung: `before`, `after`, `filter`

### 6.1. `before(Function<ServerRequest,ServerRequest>)`

Được dùng để xử lý/biến đổi functional request trước handler:

```java
.before(request -> {
    audit.info("route={} method={}",
            request.path(), request.method());
    return request;
})
```

Fragment giả định có `audit` logger. Nên log path đã kiểm soát/route template khi có thể, tránh log raw query/token.

Có thể dùng `ServerRequest.from(request)` để xây request wrapper bất biến:

```java
.before(request -> ServerRequest.from(request)
        .header("X-Lesson-Scope", "notes")
        .build())
```

Đây là minh họa request transformation. **Đừng biến một header tự thêm vào functional request thành bằng chứng authentication.** Với dữ liệu đáng tin, dùng service/validated context và chính sách phân quyền phù hợp.

### 6.2. `after(BiFunction<ServerRequest,ServerResponse,ServerResponse>)`

Sau khi handler trả `ServerResponse`, xử lý response object:

```java
.after((request, response) -> {
    audit.info("mvc_fn_status={}",
            response.statusCode().value());
    return response;
})
```

Dạng này giúp ghi metric/status của response thành công hoặc filter trả về sớm. **Không nên coi `after` là một `finally` cho mọi exceptions:** nếu downstream ném trước khi có `ServerResponse`, xử lý lỗi hoặc `filter try/finally` mới là chỗ thích hợp. Nếu trả response stream, phần xử lý **body thực tế** có thể diễn ra sau khi `after` trả về; metric ở đây chưa nhất thiết là thời gian gửi toàn bộ bytes tới client.

### 6.3. `filter(HandlerFilterFunction<...>)`

Dùng khi cần chủ động gọi hoặc bỏ qua `next.handle`:

```java
.filter((request, next) -> {
    String gate = request.headers()
            .firstHeader("X-Demo-Client");

    if (!"learning".equals(gate)) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of(
                        "code", "DEMO_HEADER_REQUIRED"));
    }

    return next.handle(request);
})
```

`before` và `after` phù hợp với biến đổi request/response đơn giản; `filter` linh hoạt hơn khi cần **short-circuit**, phối hợp trước/sau trong một `try/finally` hoặc bắt một kiểu exception xác định.

### 6.4. Dùng static adapters cho filter có sẵn

`HandlerFilterFunction` có:

- `ofRequestProcessor(Function<ServerRequest,ServerRequest>)`.
- `ofResponseProcessor(BiFunction<ServerRequest,T,R>)`.
- `ofErrorHandler(Predicate<Throwable>, BiFunction<Throwable,ServerRequest,T>)`.
- `andThen(...)` để compose filters có kiểu tương thích.
- `apply(handler)` để áp filter vào handler.

Ví dụ fragment:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> passThrough =
        HandlerFilterFunction.ofRequestProcessor(
                request -> request);

HandlerFilterFunction<ServerResponse, ServerResponse> trace =
        passThrough.andThen((request, next) -> {
            long started = System.nanoTime();
            try {
                return next.handle(request);
            } finally {
                long nanos = System.nanoTime() - started;
                // Record bounded metric only.
            }
        });
```

`andThen` compose theo thứ tự đã khai báo trong contract `HandlerFilterFunction`; khi có nhiều nested/outer builders, **đừng suy ra thứ tự chỉ từ cảm giác về decorator**. Hãy viết integration test ghi event order nếu phụ thuộc business vào thứ tự.

## 7. Xử lý lỗi bằng `RouterFunctions.Builder.onError`

Handler có thể ném exception vì resource không tồn tại, dữ liệu không hợp lệ hoặc server gặp lỗi. Với WebMvc.fn, builder hỗ trợ error mapping ngay trong router:

```java
.onError(NoteNotFoundException.class, (error, request) ->
        ServerResponse.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ApiError(
                        "NOTE_NOT_FOUND", "Note does not exist")))
```

Đây là fragment trong builder, giả định `NoteNotFoundException`/`ApiError` đã được định nghĩa. `onError` nhận:

1. Một `Class<? extends Throwable>`, hoặc
2. Một `Predicate<Throwable>` để quyết định lỗi nào được xử lý,

và một hàm sinh `ServerResponse` từ `Throwable` cùng `ServerRequest`.

### 7.1. Class-based mapping

```java
.onError(InvalidNoteException.class,
        (error, request) ->
                ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError(
                            "NOTE_INVALID", "Invalid note input")))
.onError(NoteNotFoundException.class,
        (error, request) ->
                ServerResponse.status(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError(
                            "NOTE_NOT_FOUND", "Note not found")))
```

Ưu điểm: typed business exceptions, ít phải xem message; dễ test error contract. Nên dùng **stable application error code** và message an toàn cho client, không trả raw SQL, stack traces hay token.

### 7.2. Predicate-based mapping

```java
.onError(error ->
        error instanceof IllegalArgumentException,
        (error, request) ->
                ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError(
                            "INVALID_ARGUMENT",
                            "Invalid request argument")))
```

Dùng predicate khi muốn match theo một nhóm lỗi hoặc điều kiện cụ thể, nhưng tránh `error -> true` cho tất cả rồi biến **bug nội bộ thành HTTP 400**. Một catch-all có thể che lấp lỗi lập trình, khiến monitoring bỏ sót 500.

### 7.3. `ofErrorHandler(...)` khi không dùng builder.onError

Từ filter API:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> notFound =
        HandlerFilterFunction.ofErrorHandler(
            error -> error instanceof NoteNotFoundException,
            (error, request) ->
                ServerResponse.status(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError(
                        "NOTE_NOT_FOUND", "Note not found")));
```

Filter này có thể được thêm qua `RouterFunction.filter(...)` hoặc builder `.filter(notFound)`. Chọn **một chiến lược error mapping có cấu trúc**, tránh xử lý cùng lỗi ở nhiều lớp không rõ precedence.

### 7.4. Exceptions nào thuộc trách nhiệm `onError`?

`onError` là filter bao quanh **handler function** trong phạm vi router. Nó phù hợp cho lỗi ném **khi handler/filter xử lý request sau khi router match**.

Nó không phải global exception handler cho mọi thứ:

- Lỗi xảy ra **trước route match** (Servlet filter, Security, request parsing/dispatch trước functional handler) có thể không nằm trong phạm vi.
- Lỗi của controller gắn annotation ở router khác không nhất thiết đi qua `onError` của functional builder.
- Lỗi khi **serialize/write HTTP body sau khi response đã commit** có thể không thể chuyển thành JSON error mới; tùy message converter/container.
- Router **không match** không có exception để `onError` bắt; nó thường trở thành 404 hoặc mapping/exception khác do MVC xử lý.
- Invalid JSON body có thể phát sinh exception conversion; nếu không match custom types/predicate, nó sẽ đi qua MVC exception infrastructure.
- Khi đã gửi một phần response streaming, không hứa có thể thay 200 thành 500.

`@RestControllerAdvice` / `@ExceptionHandler` / `HandlerExceptionResolver` là những cơ chế khác. Với functional endpoints, **cách tường minh nhất cho lỗi nghiệp vụ cục bộ thường là `onError`**; global MVC exception resolvers có thể tham gia tùy đường xử lý exception/adapter và Spring configuration. Không giả định advice của annotated controllers tự thay thế mọi error mapping chức năng.

### 7.5. Không lộ thông tin nhạy cảm trong lỗi

Không nên:

```java
.onError(Throwable.class, (error, request) ->
        ServerResponse.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("debug", error.toString())))
```

Đây là **anti-pattern**: exception messages có thể chứa DB paths, SQL, request body, credentials hoặc private implementation details. Thay bằng lỗi chuẩn:

```json
{"code":"INTERNAL_ERROR","message":"Unexpected server error"}
```

Log nội bộ vẫn cần phân loại/giới hạn để điều tra. Không log toàn bộ `Authorization` header, Cookie, raw JSON body hoặc giá trị path không đáng tin.

## 8. Cấu trúc code khi ứng dụng có nhiều nhóm functional routes

Một cấu trúc có thể mở rộng:

```text
src/main/java/demo/webfn/
├─ WebFnApplication.java
├─ routes/
│  ├─ PublicRoutes.java
│  ├─ NotesRoutes.java
│  └─ OrdersRoutes.java
├─ handlers/
│  ├─ NotesHandler.java
│  └─ OrdersHandler.java
├─ service/
│  ├─ NoteService.java
│  └─ OrderService.java
├─ model/
│  └─ ApiError.java
└─ filters/
   ├─ RequestMetricsFilter.java
   └─ CorrelationIdFilter.java
```

Đây là **cấu trúc minh họa**, không phải tất cả các file phải tồn tại trong demo một file ở phần 10. Phân trách nhiệm:

- **Routes** chỉ khai báo HTTP path/method/predicate, gắn filters và onError.
- **Handlers** giải mã `ServerRequest`, gọi services, xây `ServerResponse`.
- **Services** chứa nghiệp vụ, persistence, transactions, validations.
- **Filters** chỉ xử lý mối quan tâm chung trong phạm vi rõ ràng.
- **Error mapping** đưa exception types thành HTTP contracts; tránh tạo response theo raw exception messages.
- **Spring Security** xử lý authorization bắt buộc và CSRF/CORS theo kiến trúc, không đẩy trách nhiệm này vào route builder.

### 8.1. Ghép các router functions

Một số cách hợp lệ:

```java
RouterFunction<ServerResponse> combined =
        notesRouter.and(ordersRouter);
```

Hoặc:

```java
RouterFunction<ServerResponse> combined =
        RouterFunctions.route()
                .add(notesRouter)
                .add(ordersRouter)
                .build();
```

Đây là **fragments**, giả định hai routers tồn tại. Việc ghép theo thứ tự có nghĩa router nào match đầu tiên sẽ được chọn. Nếu URL patterns có overlap, thứ tự ghép là một phần của contract cần test.

### 8.2. Nhiều bean `RouterFunction` và @Order

Trong Boot MVC, một `RouterFunction<ServerResponse>` được khai báo `@Bean` được `RouterFunctionMapping` phát hiện. Khi có nhiều router function beans, framework sắp xếp/kết hợp chúng. Nếu routing priority quan trọng, hãy cấu hình thứ tự tường minh phù hợp cho bean/router, xem Bean ordering/@Order của version đang dùng, và tránh hai routers đăng ký cùng route ngoài ý muốn.

Ví dụ **fragment**:

```java
@Bean
@Order(10)
RouterFunction<ServerResponse> publicRouter() {
    return RouterFunctions.route()
            .GET("/public/status",
                request -> ServerResponse.ok().body("ready"))
            .build();
}
```

Khi cùng request match nhiều router beans, test trực tiếp precedence thay vì giả định Spring chọn “specific” hơn như annotated controllers. Trong một nhóm cùng domain, gộp thành **một router bean** giúp giảm rủi ro ambiguity và kiểm soát thứ tự dễ hơn.

### 8.3. Prefix/version tổ chức hợp đồng API

Nhóm `/api/v1`, `/api/v2` riêng để:

- Tránh rơi nhầm handler version khác.
- Có error envelope/route filters độc lập khi cần.
- Cho phép migrate từng version với test độc lập.
- Không áp dụng filter dành cho `/api/v2` lên `/health` hoặc `/api/v1` một cách vô tình.

Nếu version được đàm phán qua header/media type thay vì path, dùng predicates hợp đồng tương ứng; không mặc định cứ có prefix `/v2` là đã xử lý hết thay đổi schema và version compatibility.

## 9. Một số điều về HandlerFunction và ServerResponse

### 9.1. Đọc path variables, query, body

```java
String id = request.pathVariable("id");

String search = request.param("q").orElse("");

NewNote input = request.body(NewNote.class);
```

Đây là fragment trong handler với `ServerRequest request`. `pathVariable` chỉ hợp lệ sau route có `{id}` đã match; `param` trả `Optional<String>`. `body(Class)` dùng message converters để đọc request body theo media type/content negotiation.

Không tin dữ liệu chỉ vì nó đã thành Java object: vẫn cần domain validation, giới hạn độ dài, phân quyền. `NumberFormatException` khi parse `id` cần map thành 400 phù hợp; resource không tồn tại sau parse nên map 404.

### 9.2. Các kiểu ServerResponse

```java
ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(new Note(42, "Hello"));

ServerResponse.status(HttpStatus.NOT_FOUND)
        .contentType(MediaType.APPLICATION_JSON)
        .body(new ApiError("NOTE_NOT_FOUND", "Note not found"));

ServerResponse.created(URI.create("/api/v1/notes/42"))
        .contentType(MediaType.APPLICATION_JSON)
        .body(new Note(42, "Hello"));

ServerResponse.noContent().build();
```

Các fragments minh họa API response builder. `ServerResponse.created(uri)` tạo 201 + Location; URI root-relative giả định app ở context root. Với app sau proxy/context path, dùng URI generation phù hợp, ví dụ `ServletUriComponentsBuilder` hoặc canonical base.

### 9.3. Không nhầm functional ServerResponse với reactive Mono

Trong Servlet WebMvc.fn:

```java
HandlerFunction<ServerResponse> hello =
        request -> ServerResponse.ok().body("Hello");
```

Còn WebFlux.fn thường dùng `Mono<ServerResponse>` từ Reactor và imports `org.springframework.web.reactive.function.server`. **Không copy reactive `Mono` signatures** vào MVC sample nếu không chủ ý tích hợp reactive adapters.

## 10. Ứng dụng chạy được: Spring Boot 3.5 + Java 17

Demo dùng một `RouterFunction` bean để tránh phụ thuộc ordering giữa nhiều beans. Các endpoints:

| Endpoint | Hành vi |
| --- | --- |
| `GET /health` | Trả `OK`; **không bị notes filter chặn** |
| `GET /api/v1/notes` | Danh sách notes trong memory |
| `GET /api/v1/notes/stats` | Trả số lượng notes; được đặt **trước** `/{id}` |
| `GET /api/v1/notes/{id}` | 200 nếu tìm thấy; 404 nếu chưa có; 400 nếu ID không hợp lệ |
| `POST /api/v1/notes` | Nhận JSON, validate title, tạo record, trả 201 + Location |
| Các notes routes | Yêu cầu `X-Demo-Client: learning` từ filter minh họa; nếu thiếu trả 400 |

**Giới hạn quan trọng:** header demo không có giá trị bảo mật; client tự gửi được. Không có Spring Security/DB/transactions/tracing thật. Đây là bản học thuật về functional routes/filter/error mapping, không phải hệ thống sản xuất.

### 10.1. Dependencies

Dùng Spring Initializr chọn Java 17+, Spring Boot **3.5.x**, Gradle và **Spring Web**. Trong project đã có Boot plugin, repository/dependency management, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là fragment `build.gradle`; cần build file Gradle hoàn chỉnh do Spring Initializr hoặc project cung cấp. Starter web có Spring MVC Servlet stack và Jackson JSON converter.

### 10.2. Java source đầy đủ

Tạo file **`src/main/java/demo/webfn/WebFnApplication.java`**:

```java
package demo.webfn;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.HandlerFilterFunction;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;
import org.springframework.web.util.UriComponentsBuilder;

@SpringBootApplication
public class WebFnApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFnApplication.class, args);
    }
}

record NewNote(String title) {}

record Note(long id, String title) {}

record ApiError(String code, String message) {}

class InvalidNoteException extends RuntimeException {
    InvalidNoteException() {
        super("Invalid note");
    }
}

class NoteNotFoundException extends RuntimeException {
    NoteNotFoundException() {
        super("Note not found");
    }
}

class NotesHandler {
    private final AtomicLong sequence = new AtomicLong(1000);
    private final ConcurrentMap<Long, Note> notes =
            new ConcurrentHashMap<>();

    ServerResponse list(ServerRequest request) {
        List<Note> result = notes.values().stream()
                .sorted(Comparator.comparingLong(Note::id))
                .toList();

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(result);
    }

    ServerResponse stats(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("count", notes.size()));
    }

    ServerResponse get(ServerRequest request) {
        long id;
        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException ex) {
            throw new InvalidNoteException();
        }

        Note note = notes.get(id);
        if (note == null) {
            throw new NoteNotFoundException();
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }

    ServerResponse create(ServerRequest request) throws Exception {
        NewNote input = request.body(NewNote.class);
        if (input == null || input.title() == null
                || input.title().isBlank()
                || input.title().length() > 100) {
            throw new InvalidNoteException();
        }

        long id = sequence.incrementAndGet();
        Note note = new Note(id, input.title().trim());
        notes.put(id, note);

        // Request URI chứa /api/v1/notes, bỏ query cũ.
        URI location = UriComponentsBuilder
                .fromUri(request.uri())
                .replaceQuery(null)
                .pathSegment("{id}")
                .encode()
                .buildAndExpand(id)
                .toUri();

        return ServerResponse.created(location)
                .contentType(MediaType.APPLICATION_JSON)
                .body(note);
    }
}

@Configuration
class FunctionalRoutesConfig {
    private static final Logger log =
            LoggerFactory.getLogger(FunctionalRoutesConfig.class);

    @Bean
    NotesHandler notesHandler() {
        return new NotesHandler();
    }

    private HandlerFilterFunction<ServerResponse, ServerResponse>
    notesDemoFilter() {
        return (request, next) -> {
            String client = request.headers()
                    .firstHeader("X-Demo-Client");

            if (!"learning".equals(client)) {
                return ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(new ApiError(
                                "DEMO_HEADER_REQUIRED",
                                "X-Demo-Client must be learning"));
            }

            long started = System.nanoTime();
            try {
                return next.handle(request);
            } finally {
                long elapsed = System.nanoTime() - started;
                log.info("notes_route durationMicros={}",
                        elapsed / 1_000L);
            }
        };
    }

    @Bean
    RouterFunction<ServerResponse> applicationRoutes(
            NotesHandler handler) {

        return RouterFunctions.route()
                // Không chịu notes filter.
                .GET("/health", request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .body("OK"))

                // Tất cả routes bên trong dùng shared policies.
                .path("/api/v1", api -> api

                    // Static path trước path variable.
                    .GET("/notes/stats", handler::stats)
                    .GET("/notes/{id}", handler::get)
                    .GET("/notes", handler::list)
                    .POST("/notes", handler::create)

                    .before(request -> {
                        log.info("notes_request method={}",
                                request.method());
                        return request;
                    })

                    .filter(notesDemoFilter())

                    .after((request, response) -> {
                        log.info("notes_response status={}",
                                response.statusCode().value());
                        return response;
                    })

                    .onError(InvalidNoteException.class,
                        (error, request) ->
                            ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .body(new ApiError(
                                        "NOTE_INVALID",
                                        "Invalid note input")))

                    .onError(NoteNotFoundException.class,
                        (error, request) ->
                            ServerResponse.status(HttpStatus.NOT_FOUND)
                                .contentType(MediaType.APPLICATION_JSON)
                                .body(new ApiError(
                                        "NOTE_NOT_FOUND",
                                        "Note does not exist"))))
                .build();
    }
}
```

**Cấu trúc Java:** file có một top-level class public (`WebFnApplication`), còn các records/classes còn lại package-private. Java 17 hỗ trợ `record` và `Stream#toList()`. Spring Boot component scan từ `demo.webfn` tìm `FunctionalRoutesConfig`. Bean `applicationRoutes` được Spring MVC `RouterFunctionMapping` phát hiện.

**Lưu ý compiler:** các method references `handler::list`, `handler::stats`, `handler::get`, `handler::create` đều nhận `ServerRequest` và trả `ServerResponse`. `create` khai báo `throws Exception`, phù hợp `HandlerFunction#handle`. `UriComponentsBuilder.fromUri(request.uri())` nhận `URI` và không cần current request holder. `replaceQuery(null)` loại query request cũ; `pathSegment("{id}")` + `encode()` + `buildAndExpand(id)` giữ ID thành URI segment.

**Lưu ý dữ liệu demo:** in-memory map chỉ có trong một JVM; restart mất dữ liệu và nhiều nodes không chia sẻ state. Để đưa vào production cần service/database, transactions, auth/authorization, input validation và concurrency policies theo sản phẩm.

### 10.3. Cách chạy

```bash
./gradlew bootRun
```

**Public health, không cần demo header:**

```bash
curl -i 'http://localhost:8080/health'
```

Kỳ vọng `200 OK` và body:

```text
OK
```

**Notes endpoint thiếu header:**

```bash
curl -i 'http://localhost:8080/api/v1/notes'
```

Kỳ vọng `400 Bad Request` với JSON:

```json
{
  "code": "DEMO_HEADER_REQUIRED",
  "message": "X-Demo-Client must be learning"
}
```

**Danh sách notes khi có header:**

```bash
curl -i 'http://localhost:8080/api/v1/notes' \
  -H 'X-Demo-Client: learning'
```

Ban đầu (trước khi POST) body dự kiến:

```json
[]
```

**Tạo note:**

```bash
curl -i -X POST \
  'http://localhost:8080/api/v1/notes?source=docs' \
  -H 'X-Demo-Client: learning' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Functional MVC"}'
```

Với request tạo đầu tiên, kết quả dự kiến:

```http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/v1/notes/1001
Content-Type: application/json

{"id":1001,"title":"Functional MVC"}
```

`source=docs` **không** xuất hiện ở Location nhờ `replaceQuery(null)`. ID 1001 chỉ là kết quả của counter ban đầu khi chưa có request tạo khác.

**Đọc note:**

```bash
curl -i \
  'http://localhost:8080/api/v1/notes/1001' \
  -H 'X-Demo-Client: learning'
```

Kỳ vọng 200 và body note tương ứng.

**Truy cập route static `stats`:**

```bash
curl -i \
  'http://localhost:8080/api/v1/notes/stats' \
  -H 'X-Demo-Client: learning'
```

Sau đúng một lần POST, body:

```json
{"count":1}
```

Nếu đặt `/{id}` trước `/stats`, string `"stats"` có thể bị parse như số ID và trả lỗi. Ví dụ thực tế đặt route static trước.

**Nhập ID không phải số:**

```bash
curl -i \
  'http://localhost:8080/api/v1/notes/abc' \
  -H 'X-Demo-Client: learning'
```

Handler ném `InvalidNoteException` và `onError` trả 400:

```json
{"code":"NOTE_INVALID","message":"Invalid note input"}
```

**ID hợp lệ nhưng không tồn tại:**

```bash
curl -i \
  'http://localhost:8080/api/v1/notes/999999' \
  -H 'X-Demo-Client: learning'
```

Dự kiến 404 và:

```json
{"code":"NOTE_NOT_FOUND","message":"Note does not exist"}
```

Trên môi trường khác (đặc biệt sau proxy/context path), Location host/prefix hoặc headers phụ thuộc request thực và deployment. Các ví dụ HTTP minh họa output contract, **không phải log đã chạy Gradle**.

## 11. Kiểm thử MVC functional routes bằng MockMvc

`MockMvc` khởi động MVC test/request infrastructure mà không cần mở cổng mạng. Test này dùng `@SpringBootTest` để bảo đảm Spring Boot tìm được `RouterFunction` bean và `@AutoConfigureMockMvc` để thực hiện request.

Tạo **`src/test/java/demo/webfn/WebFnApplicationTests.java`**:

```java
package demo.webfn;

import java.net.URI;
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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebFnApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void healthIsNotAffectedByNestedFilter() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("OK"));
    }

    @Test
    void notesFilterShortCircuitsWithoutClientHeader()
            throws Exception {
        mvc.perform(get("/api/v1/notes"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("DEMO_HEADER_REQUIRED"));
    }

    @Test
    void staticStatsRouteWinsBeforeVariableRoute()
            throws Exception {
        mvc.perform(get("/api/v1/notes/stats")
                .header("X-Demo-Client", "learning"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").isNumber());
    }

    @Test
    void invalidIdUsesFunctionalOnError400()
            throws Exception {
        mvc.perform(get("/api/v1/notes/not-a-number")
                .header("X-Demo-Client", "learning"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("NOTE_INVALID"));
    }

    @Test
    void missingNoteUsesFunctionalOnError404()
            throws Exception {
        mvc.perform(get("/api/v1/notes/999999999")
                .header("X-Demo-Client", "learning"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                    .value("NOTE_NOT_FOUND"));
    }

    @Test
    void postCreatesResourceAndLocationHasNoOldQuery()
            throws Exception {

        MvcResult response = mvc.perform(
                post("/api/v1/notes?source=docs")
                    .header("X-Demo-Client", "learning")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"title":"Created with WebMvc.fn"}
                        """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title")
                    .value("Created with WebMvc.fn"))
            .andReturn();

        String location = response.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);

        URI uri = URI.create(location);
        assertTrue(uri.getPath().matches(
                "/api/v1/notes/[0-9]+"));
        assertTrue(uri.getRawQuery() == null);

        mvc.perform(get(uri.getRawPath())
                .header("X-Demo-Client", "learning"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title")
                    .value("Created with WebMvc.fn"));
    }

    @Test
    void blankTitleUsesFunctionalOnError400()
            throws Exception {
        mvc.perform(post("/api/v1/notes")
                .header("X-Demo-Client", "learning")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"   "}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("NOTE_INVALID"));
    }
}
```

Chạy:

```bash
./gradlew test
```

**Bảy tests được thiết kế để pass với code và Spring Boot 3.5 baseline nêu trên**. Đây là các kết quả dự kiến từ phân tích mã và Spring API, **chưa phải chứng cứ Gradle đã chạy**. Các tests không assert ID cố định hoặc count chính xác (ngoại trừ kiểu number) để hạn chế phụ thuộc test order/shared Spring context.

Các phép kiểm tra có ý nghĩa:

- `/health` không cần header → nested filter không lan lên top-level route.
- `/notes` không header → `filter` short-circuit trước handler.
- `/notes/stats` trả JSON stats, không đi nhầm `/{id}`.
- ID không phải số → 400 từ `onError(InvalidNoteException.class,...)`.
- ID số không tồn tại → 404 từ `onError(NoteNotFoundException.class,...)`.
- POST tạo note → 201 và Location không chứa query cũ.
- POST title blank → 400 theo business validation mapping.

### 11.1. Test phạm vi filter và error mapping bằng negative cases

Những test bổ sung có giá trị:

- Gọi `/health` kèm header bất kỳ, assert nó không thay đổi behavior.
- Gọi `/api/v1/notes/foo` không demo header: filter short-circuit trả lỗi header, **chưa vào parser ID**, theo hợp đồng ví dụ.
- Gọi endpoint không match như `/does-not-exist`: onError của notes router **không** biến 404 đó thành lỗi NOTE_NOT_FOUND.
- Gửi JSON sai syntax với `Content-Type: application/json`: xác minh error response thực do message converter/MVC infrastructure sinh, không khẳng định tự map NOTE_INVALID.
- Đưa cùng path vào một router khác hoặc add catch-all trước: test route shadowing.
- Nếu có Security starter, test unauthorized access ở Servlet security filter layer, không chỉ header demo.
- Gửi request với context path và proxy headers trong integration test nếu Location phải là external URL.

### 11.2. Khi nào cần test server thật?

`MockMvc` xác minh route, handler, filter và onError của MVC mà không chạy đầy đủ embedded socket/gateway. Khi cần kiểm tra:

- Servlet filter registrations, CORS preflight và security chain.
- Proxy/Host/Forwarded URL generation.
- Real content negotiation/compression/HTTP headers.
- Multipart lớn, streaming, disconnects/timeouts.
- Multiple nodes/load balancing hoặc transaction consistency.

Hãy dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` + HTTP client thật, và test staging qua gateway khi chính sách phụ thuộc proxy/CDN.

## 12. `HandlerFilterFunction` và thứ tự thực thi filters

Hình dung một filter lồng nhau:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> a =
        (request, next) -> {
            events.add("A-in");
            try {
                return next.handle(request);
            } finally {
                events.add("A-out");
            }
        };

HandlerFilterFunction<ServerResponse, ServerResponse> b =
        (request, next) -> {
            events.add("B-in");
            try {
                return next.handle(request);
            } finally {
                events.add("B-out");
            }
        };
```

Đây là fragment, `events` là danh sách được cấp trong test; nếu được dùng đồng thời, cần thread-safe instrumentation hoặc request-scoped event list.

Một chain cụ thể `a.andThen(b).apply(handler)` có luồng khái niệm:

```text
A-in
  B-in
    handler
  B-out
A-out
```

Trong thực tế, builder/nested router còn có các lớp filter khác, `before`/`after`/`onError` và thứ tự wrap. Khi thứ tự ảnh hưởng quyền truy cập hoặc logging, hãy assert event order trong test. **Không dựa vào nhãn tên filter hoặc thứ tự @Bean registration không được chỉ định**.

### 12.1. Filter chain không bảo đảm truy cập body an toàn nhiều lần

Nếu một handler filter đọc `request.body(NewNote.class)` để validate và handler lại đọc body lần hai, Servlet request body có thể đã bị tiêu thụ. Không viết một filter JSON logging đọc toàn body rồi tin downstream vẫn deserialize bình thường.

Giải pháp:

- Validation domain ở handler/service sau khi parse một lần.
- Nếu filter buộc phải kiểm tra raw payload, dùng buffering wrapper đúng cấu hình/giới hạn hoặc thay kiến trúc.
- Không log raw credentials/PII/Authorization.
- Cẩn thận với multipart large body, stream và memory limits.
- Nếu cần audit event, ghi metadata đã xác minh thay vì toàn request content.

### 12.2. Dùng try/finally cho MDC

Nếu dùng `MDC` cho correlation ID trong filter, luôn cleanup:

```java
return (request, next) -> {
    String requestId = UUID.randomUUID().toString();
    MDC.put("requestId", requestId);
    try {
        return next.handle(request);
    } finally {
        MDC.remove("requestId");
    }
};
```

Đây là fragment với imports `java.util.UUID`, `org.slf4j.MDC`. Filter chỉ bao quanh **handler invocation**; nếu response body streaming viết sau đó trên thread khác, MDC có thể không còn, và cần context propagation riêng. Nếu muốn correlation ID từ sớm cho Servlet filter/error response, cân nhắc filter tầng Servlet hoặc framework tracing/observability.

## 13. Xử lý lỗi: phân loại theo “không match”, “client error” và “server error”

### 13.1. Không match route ≠ exception trong handler

Ví dụ GET `/api/v1/unknown` có thể không match functional router nào. `onError(NoteNotFoundException.class,...)` **không** được gọi chỉ vì request trở thành 404.

Với một route đã match nhưng note ID không có trong repository, handler ném `NoteNotFoundException`: đây mới là lỗi nghiệp vụ được `onError` ánh xạ thành 404. Hai trường hợp cùng status nhưng nguồn và error body có thể khác.

### 13.2. Bad request vs not found

| Trường hợp | Status nên dùng | Nguồn xử lý |
| --- | --- | --- |
| Thiếu demo header theo contract bài học | 400 | Short-circuit trong `HandlerFilterFunction` |
| ID không parse được theo `/{id}` | 400 | `InvalidNoteException` → `onError` |
| ID hợp lệ nhưng record không tồn tại | 404 | `NoteNotFoundException` → `onError` |
| Route không tồn tại | 404 (thường gặp) | MVC handler mapping / default error handling |
| Body JSON cú pháp sai | 400 (thường gặp) | Message converter + MVC exception infrastructure |
| Unsupported request media type | Có thể 415 tùy routes/config | Predicate/HTTP handling và explicit error contract |
| Method không phù hợp | Có thể 405 hoặc fallback handling tùy mappings | Request mapping/resolvers |
| Chưa xác thực | 401 | Spring Security authentication |
| Đã xác thực nhưng không đủ quyền | 403 | Spring Security authorization |
| Server code/persistence lỗi không lường trước | 500 | Error infrastructure/monitoring |

Không biến mọi exception thành 200 với `{"ok":false}`. HTTP status là một phần quan trọng của public API.

### 13.3. Response đã commit có giới hạn

Nếu một handler/filter tạo streaming response và lỗi phát sinh **sau khi bytes đầu tiên đã được gửi**, `onError` có thể không thể thay headers hoặc status. Đây là vấn đề vòng đời HTTP/Servlet, không riêng functional APIs.

Muốn truyền lỗi trong stream đã mở, phải có framing/error protocol bên trong stream (ví dụ event type "error" trong SSE), hoặc để client xử lý disconnect/retry. Đừng trả stack trace theo body đang mở.

## 14. Functional routes có thể cùng tồn tại với annotated controllers không?

Có. Trong Spring MVC, `RouterFunctionMapping` và annotated `RequestMappingHandlerMapping` đều là các handler mapping dưới `DispatcherServlet`. Một app có thể vừa có:

```java
@RestController
class LegacyController {
    @GetMapping("/legacy/ping")
    String ping() {
        return "pong";
    }
}
```

vừa có:

```java
@Bean
RouterFunction<ServerResponse> functionalRouter() {
    return RouterFunctions.route()
            .GET("/new/ping",
                request -> ServerResponse.ok().body("pong"))
            .build();
}
```

Hai fragment minh họa chạy song song trong một Boot MVC application. Tuy nhiên:

- `HandlerFilterFunction` trên `/new/ping` không tự chạy cho `/legacy/ping`.
- `@ControllerAdvice`, interceptors, HandlerAdapters và message converters có phạm vi/semantics riêng.
- Nếu annotated controller và functional router đăng ký **cùng method/path**, handler mapping order quyết định ai nhận request; dễ gây bất ngờ.
- Tổ chức routes tránh overlap giữa functional và annotated styles, đặc biệt khi migrate từng module.
- Security policy theo paths/methods phải bao phủ cả hai, không chỉ một kiểu controller.

Một chiến lược migration phù hợp là chuyển từng bounded module (ví dụ `/api/v2/catalog/**`), test API contract, giữ annotation controllers còn lại, rồi đánh giá độ phức tạp trước khi chuyển tiếp.

## 15. CORS, Security và Observability

### 15.1. Spring Security và CORS

Tài liệu WebMvc.fn ghi rõ CORS support cho functional endpoints được cung cấp qua **`CorsFilter` chuyên dụng**. Không mặc định rằng functional builder có mọi hỗ trợ CORS annotation giống controller annotation.

Với API có cross-origin clients:

- Cấu hình `CorsFilter` hoặc Spring Security CORS integration phù hợp Servlet filter chain.
- Xác minh preflight `OPTIONS` được xử lý đúng **trước lớp authentication thích hợp**.
- Không dùng `Access-Control-Allow-Origin: *` khi trả credentials/cookies cross-origin.
- CORS không thay authentication/authorization/CSRF; client bên ngoài browser không bị CORS hạn chế.
- Nếu sử dụng cookies với state-changing requests, thiết kế CSRF và SameSite theo threat model.

Header mô phỏng `X-Demo-Client` trong code mẫu **không phải security control**. Client có thể gửi bất kỳ giá trị. Muốn bảo vệ thật, xây `SecurityFilterChain`, xác thực bearer token/session và phân quyền từng tài nguyên.

### 15.2. Metric/logging fields an toàn

Nên thu thập:

- Route template/operation name, HTTP method và status class.
- Latency bucket, count/error rate.
- Correlation ID do server hoặc hạ tầng tin cậy sinh.
- Exception type/error code đã phân loại, không phải raw exception messages.
- Tenant/user pseudonymous ID theo privacy policy nếu cần.

Không ghi raw request bodies, Authorization headers, cookies, password, OTP, access tokens hoặc query parameters nhạy cảm. Nếu log request path có resource IDs/PII, thay bằng template hoặc hash/pseudonymization được thiết kế đúng.

`HandlerFilterFunction` có thể đo thời gian đồng bộ quanh `next.handle`, **không nhất thiết đo hết thời gian truyền body streaming**, timeout hoặc network latency. Khi cần metrics toàn bộ HTTP lifecycle, dùng Servlet filters/observability framework ở đúng tầng.

## 16. Dùng `HandlerFilterFunction` khi nào? Dùng cơ chế khác khi nào?

| Mục tiêu | Cơ chế hợp lý | Vì sao |
| --- | --- | --- |
| Thực hiện kiểm tra trước một nhóm functional routes | `RouterFunctions.Builder.filter` | Chỉ áp route group match, có quyền short-circuit |
| Biến đổi functional request đơn giản | `before` | Code rõ, không cần tự gọi next |
| Ghi status sau handler function | `after` | Nhận `ServerResponse` đã tạo |
| Chuyển domain exception thành HTTP body cho nhóm routes | `onError` | Error mapping cục bộ, explicit |
| Reuse filter trên một router function đã build | `RouterFunction.filter(...)` | Composition sau khi có router |
| CORS preflight và servlet-level concerns | `CorsFilter`/Servlet Filter | Chạy trước functional routing |
| Xác thực/ủy quyền mọi entry points | `SecurityFilterChain` | Bảo vệ thống nhất HTTP layer |
| Intercept annotated controller handler | `HandlerInterceptor` | Biết MVC handler execution context |
| Global exception/ProblemDetail policies | MVC exception infrastructure/`@ControllerAdvice` với test tương thích | Không giới hạn một router riêng |
| Streaming HTTP response | `ServerResponse` streaming API hoặc MVC streaming APIs | Chú ý async/response commit |
| Event/log tracing toàn request kể cả not matched | Servlet filter/observation pipeline | Handler filter chỉ chạy sau route match |

Khi ứng dụng còn rất nhỏ, ba routes và một filter có thể đặt trong một class. Khi domain có nhiều routes, tách router, handler, service và filter theo module để tránh “God Config” khó đọc.

## 17. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| Filter không chạy trên controller annotation | Filter chỉ gắn một functional router | Phân biệt `HandlerFilterFunction` và Servlet Filter |
| Filter notes vô tình chạy ở /health | Đặt `.filter(...)` trên outer builder | Chuyển filter vào nested builder, thêm test |
| GET /notes/stats đi vào get ID | Route `/{id}` trước static route | Đổi thứ tự, test output stats |
| Route không match nhưng onError không chạy | Chưa có selected handler/exception | Phân biệt 404 mapping vs exception |
| JSON sai format trả error body khác mong đợi | Message converter/MVC resolver xử lý | Test invalid JSON, config global error |
| Return 200 nhưng body vẫn báo lỗi | Exception bị bắt và trả body success vô ý | Sử dụng HTTP status đúng |
| Exception bị leak raw message trong JSON | Error handler trả `error.toString()` | Stable safe error code/message |
| Header gate xem như authentication | Header do client tự gửi | Dùng Spring Security |
| Code đã đặt filter nhưng hầu như không log | Không có route match hoặc filter scope sai | Log selected route, kiểm tra mapping |
| Hành vi khác khi chia nhiều @Bean routers | Bean order/route overlaps | Giảm overlap, explicit order và tests |
| Route group version v1/v2 chọn nhầm | Path/predicate overlap và first match | Gộp theo group, test mỗi version |
| `ServerRequest.body(...)` đọc xong không đọc lại được | Body stream đã bị tiêu thụ | Deserialize một lần, không double-read |
| before gắn header nhưng downstream thấy giá trị lạ | Header addition/duplicate từ client | Không dùng request header làm trusted identity |
| after không chạy với exception | Không có response thành công trước throw | try/finally hoặc onError đúng |
| Filter try/finally metric ngắn hơn full download | `ServerResponse` body có thể write sau | Đo Servlet lifecycle end-to-end |
| Boot không phát hiện route | Thiếu `@Bean`/component scan hoặc sai WebFlux imports | Kiểm tra router bean, WebMvc.fn package |
| Controller annotation có mapping trùng router | HandlerMapping ordering | Tránh overlapping, test |
| CORS preflight bị 401/403 | Chưa có proper CorsFilter/Security integration | Kiểm tra Servlet filter ordering |
| Test MockMvc không như server thật | Filter/proxy/container behaviors chưa được mô phỏng | RANDOM_PORT + gateway tests |

### Quy trình debug

1. Xác nhận app dùng Spring MVC (`spring-webmvc`), không nhầm WebFlux.
2. Xác nhận `RouterFunction<ServerResponse>` tồn tại là Spring bean.
3. Kiểm tra HTTP method, path, query, Accept, Content-Type.
4. Kiểm tra thứ tự tuyến khai báo và route shadowing.
5. Kiểm tra nested/outer scopes của before/after/filter/onError.
6. Nếu route match, xem filter có gọi `next.handle(request)` không.
7. Nếu handler ném exception, xác minh onError predicate/class match.
8. Nếu vẫn lỗi, xem HandlerExceptionResolver/Boot error handling.
9. Kiểm tra response status, Location, JSON body theo API contract.
10. Nếu lỗi chỉ xảy ra ở production, kiểm tra Servlet Filter/Security/proxy/tracing trước MVC.

## 18. So sánh version Spring

| Môi trường | Điểm cần chú ý |
| --- | --- |
| Spring Framework 5.2+ / Boot 2.x | WebMvc.fn có từ Spring 5.2; nhiều Servlet APIs dùng `javax.servlet.*` |
| Spring Framework 6.2 / Boot 3.5 | Java 17+, Jakarta Servlet `jakarta.servlet.*`, WebMvc.fn builder và error handler theo ví dụ |
| Spring Framework 7.x / Boot 4.x | Concepts functional routes/filters tiếp tục phát triển; starter và test infrastructure có thể đổi; đọc Javadoc đúng version |

Không copy signatures `Mono<ServerResponse>` và import reactive package từ WebFlux.fn vào code WebMvc.fn. Một vài phương thức mới như API-version-aware route predicates có thể chỉ xuất hiện ở những phiên bản Framework mới hơn; không lén dùng method của Spring 7 khi code ví dụ nhắm Spring 6.2.

Các nguồn chi tiết của WebMvc.fn có thể cùng xuất hiện trong Spring Framework docs và Javadoc của `org.springframework.web.servlet.function`. Khi nâng Boot major, kiểm tra:

- RouterFunctions.Builder method overloads.
- ServerRequest/ServerResponse serialization, message converters.
- Dependency `spring-boot-starter-web`/MVC starter của version.
- Spring Security CORS integration.
- MockMvc test imports/autoconfig.
- RouterFunctionMapping bean ordering và path matching.
- Error formatting/ProblemDetail policy.

## 19. Checklist triển khai thực tế

- [ ] RouterFunction bean chỉ chứa các routes đúng module/version.
- [ ] Static paths trước variable/wildcard paths khi overlap.
- [ ] Method/media type predicates hợp đồng rõ ràng.
- [ ] Nested path filters không vô tình áp ra top-level routes.
- [ ] Shared filter luôn gọi next khi request hợp lệ.
- [ ] Short-circuit status/body đúng và không dùng user-controlled demo header làm auth.
- [ ] before/after phù hợp lifecycle; try/finally cho cleanup.
- [ ] onError match domain exceptions có chủ đích, không bắt mọi throwable thành 400.
- [ ] Thông điệp lỗi public không lộ exception internals/secrets.
- [ ] Missing route và missing resource có error contracts/test phân biệt.
- [ ] ServerRequest body chỉ parse cần thiết; giới hạn input và validate.
- [ ] Security/CORS/CSRF áp ở đúng Servlet/Security layer.
- [ ] Multiple router beans được compose/order có chủ đích, không overlap.
- [ ] Tests bao gồm route order, nested filter, onError 400/404, POST Location.
- [ ] Có HTTP integration tests cho môi trường proxy/security nếu quan trọng.
- [ ] Functional routes và annotated controllers không đăng ký trùng mapping.
- [ ] Metrics/logging dùng route template, không log secrets.
- [ ] Tài liệu API mô tả chính xác success/error schema và status.

## 20. Bài tập thực hành

1. Trong demo, đưa `GET("/notes/{id}")` lên trước `GET("/notes/stats")`. Điều gì xảy ra với `GET /api/v1/notes/stats` và vì sao?
2. Di chuyển `.filter(notesDemoFilter())` từ nested builder lên outer builder. `GET /health` còn trả 200 khi thiếu header hay không?
3. Viết `HandlerFilterFunction` đo latency bằng `try/finally`. Vì sao số này có thể chưa bằng HTTP response end-to-end với stream body?
4. Chuyển quy tắc header demo từ `filter` sang `before`. Vì sao `before` không phù hợp khi muốn short-circuit theo cách tường minh như trên?
5. Dùng `ServerRequest.from(request)` để tạo request wrapper có thêm demo header. Tại sao không dùng giá trị này như authenticated principal?
6. Tạo record `ApiError` theo contract gồm `code` và `message`; thêm onError cho một exception nghiệp vụ mới.
7. Một request không match route nào nhận 404. Vì sao `onError(NoteNotFoundException.class,...)` không chắc được gọi?
8. Một POST có malformed JSON khiến framework báo 400. Hãy xác minh exception resolver nào xử lý; có nên dùng catch-all onError không?
9. Thêm GET `/api/v2/notes` với schema khác, tách filter và error contract theo version rồi viết tests.
10. Đặt cùng URL vào một annotated controller và một RouterFunction bean. Quan sát handler mapping order; vì sao không nên làm trong sản phẩm?
11. Tách demo một file thành `NotesRoutes`, `NotesHandler`, `NotesService` và `ApiError` mà vẫn giữ tests pass.
12. Viết một filter trả 429 khi rate limit đạt ngưỡng **với counters server-side**, không dựa vào header do client tự gửi. Vì sao nên dùng gateway/Security rate limiter cho nhiều entry points?
13. Với Spring Security bật, giải thích vì sao `HandlerFilterFunction` không thay thế `SecurityFilterChain`.
14. Tại sao một `@ControllerAdvice` của annotated controllers không nên được giả định bao phủ mọi lỗi WebMvc.fn mà chưa test?
15. Gắn `.after(...)` log status và cho handler ném exception. Có bao giờ after không chạy? Khi nào nên đặt metric ở Servlet observation layer?
16. Dùng `RouterFunctions.route().add(ordersRouter).add(notesRouter)`, phân tích ảnh hưởng nếu hai routers overlap.
17. Thêm một request predicate `accept(MediaType.APPLICATION_JSON)`. Phân biệt với `contentType(APPLICATION_JSON)`.
18. Thiết kế test MockMvc xác minh filter short-circuit trước khi handler tạo record trong database.
19. Hãy xây error response nhất quán cho unknown route và unknown resource với `ProblemDetail`/MVC error infrastructure, nhưng không bắt nhầm 401/403.
20. Nếu app phải chạy trên Spring Boot 4, các API starter/test và framework version nào cần kiểm tra trước khi copy ví dụ?

## 21. Tài liệu chính thức

- [Spring Framework 6.2 — WebMvc.fn Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): RouterFunction, HandlerFunction, nested routes, filters, route matching order, server execution.
- [Spring Framework 6.2 — RouterFunctions.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/function/RouterFunctions.Builder.html): GET/POST/path/nest/add/filter/before/after/onError overloads.
- [Spring Framework 6.2 — HandlerFilterFunction Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/function/HandlerFilterFunction.html): filter(request,next), composition, ofErrorHandler, request/response adapters.
- [Spring Framework 6.2 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/function/ServerRequest.html): body, pathVariable, params, URI and headers.
- [Spring Framework 6.2 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/function/ServerResponse.html): ok/created/status/build/body.
- [Spring Framework 6.2 — RouterFunction Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/function/RouterFunction.html): route, and, andRoute, filter.
- [Spring Framework 6.2 — MVC Exception Handling](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/exceptionhandlers.html): HandlerExceptionResolver pipeline.
- [Spring Framework 6.2 — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): RFC 9457 ProblemDetail and MVC error architecture.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): MVC auto-configuration, RouterFunction integration.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): Servlet MVC handler testing.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): SecurityFilterChain; not replaced by WebMvc.fn filters.

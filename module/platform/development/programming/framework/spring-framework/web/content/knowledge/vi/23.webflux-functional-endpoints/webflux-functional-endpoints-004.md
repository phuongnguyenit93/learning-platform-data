# Nesting, hợp thành router và tổ chức tuyến theo tính năng trong Spring WebFlux

## 1. Tổng quan: vì sao không đặt tất cả route vào một class?

Ứng dụng Spring WebFlux dùng functional endpoints thường bắt đầu với vài route:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/api/books", bookHandler::list)
        .GET("/api/books/{id}", bookHandler::byId)
        .POST("/api/books", bookHandler::create)
        .GET("/api/authors", authorHandler::list)
        .GET("/api/authors/{id}", authorHandler::byId)
        .build();
~~~

Đây là đoạn minh họa cần các handler beans đã được khai báo. Khi API phát triển, một file cấu hình chứa hàng trăm `GET/POST/PUT/DELETE` rất khó đọc: lặp prefix `/api`, trùng điều kiện `Accept: application/json`, khó xác định route nào match trước, và nhóm sách có thể ảnh hưởng nhóm tác giả.

**Nesting** (lồng router/predicate) và **composition** (hợp thành nhiều RouterFunction) giúp thiết kế:

~~~text
/api
├── /health
├── /books                 Book feature
│   ├── GET               danh sách
│   ├── GET /featured     tuyến cụ thể
│   ├── GET /{id}         tuyến có path variable
│   └── POST              tạo sách
└── /authors               Author feature
    ├── GET               danh sách
    └── GET /{id}         chi tiết
~~~

Mỗi feature có thể tự sở hữu handler + router + DTO/service, còn một lớp composition gắn base path cho cả hệ thống. Cách này đặc biệt hữu ích trong codebase có nhiều bounded contexts, multiple teams hoặc API versions.

**Điểm cần nhớ:** các tuyến được chọn **theo thứ tự hợp thành**. Nesting chỉ tổ chức matching; nó không tự cung cấp authentication, validation, thread isolation hay database transactions.

### Kết quả học tập

Sau bài, bạn có thể:
- Phân biệt `RouterFunction<ServerResponse>`, `RequestPredicate`, `HandlerFunction<ServerResponse>` và reactive `ServerResponse`.
- Dùng `RouterFunctions.route()`, `RouterFunctions.nest(...)`, builder `path(...)` và `nest(...)`.
- Ghép router bằng `RouterFunction.and(...)`, `andRoute(...)` và builder `add(...)`.
- Thiết kế module router có **child paths tương đối**, compose tại một điểm duy nhất.
- Hiểu độ ưu tiên của static route, path variable, catch-all, Accept/Content-Type và fallback.
- Biết phạm vi filter `before/after/filter/onError` khi đặt trong/ngoài nested group.
- Tránh import nhầm Servlet WebMvc.fn vào reactive WebFlux.fn.
- Chạy ví dụ Java 17 / Spring Boot 3.3.5, Book và Author routers độc lập, WebTestClient kiểm thử.
- Đánh giá CORS, Spring Security, lỗi, tracing và OpenAPI ở hệ thống nhiều router.

## 2. Phải chọn đúng WebFlux.fn, không phải WebMvc.fn

Hai framework có classes gần như cùng tên:

| Spring WebFlux.fn reactive | Spring WebMvc.fn Servlet |
| --- | --- |
| `org.springframework.web.reactive.function.server.RouterFunction` | `org.springframework.web.servlet.function.RouterFunction` |
| `org.springframework.web.reactive.function.server.RequestPredicate` | `org.springframework.web.servlet.function.RequestPredicate` |
| `org.springframework.web.reactive.function.server.ServerRequest` | `org.springframework.web.servlet.function.ServerRequest` |
| `org.springframework.web.reactive.function.server.ServerResponse` | `org.springframework.web.servlet.function.ServerResponse` |
| Handler trả `Mono<ServerResponse>` | Handler trả `ServerResponse` |
| `ServerResponse.ok().bodyValue(value)` | `ServerResponse.ok().body(value)` |
| `RequestPredicates.queryParam(...)` | `RequestPredicates.param(...)` |
| Reactor/WebFlux runtime | Servlet MVC runtime |

Trong **Spring WebFlux.fn** signature là:

~~~java
@FunctionalInterface
interface HandlerFunction<T extends ServerResponse> {
    Mono<T> handle(ServerRequest request);
}
~~~

Đây là dạng giản lược của interface để học, không phải file Java cần tự chép vào project. Framework quản lý subscription và viết HTTP response khi `Mono<ServerResponse>` hoàn thành.

Không thêm `spring-boot-starter-web` vào ví dụ chỉ vì Spring có chữ “web”: khi cả MVC và WebFlux starters cùng có mặt, Spring Boot thường chọn MVC web application type theo default. Ví dụ chạy WebFlux/Netty chỉ dùng `spring-boot-starter-webflux`.

## 3. Những thành phần xuất hiện trong một router

### 3.1. `ServerRequest`

Đọc path variable, query parameter, headers và body:

~~~java
String id = request.pathVariable("id");
String q = request.queryParam("q").orElse("");
MediaType accept = request.headers().accept().stream()
        .findFirst().orElse(MediaType.ALL);
Mono<CreateBook> input = request.bodyToMono(CreateBook.class);
~~~

Mã fragment trên cần `ServerRequest request`, `MediaType` và `CreateBook`. `bodyToMono` sử dụng reactive codecs và không nên gọi `.block()` trong handler. Path variable ban đầu là String; hãy parse/validate trước khi tìm entity.

### 3.2. `ServerResponse`

Dạng fluent reactive:

~~~java
Mono<ServerResponse> ok =
        ServerResponse.ok().bodyValue(book);

Mono<ServerResponse> created =
        ServerResponse.created(URI.create("/api/books/3"))
                .bodyValue(book);

Mono<ServerResponse> missing =
        ServerResponse.notFound().build();
~~~

Ba snippets giả định `book` và imports đã có. `ServerResponse.ok()` tạo response builder; `bodyValue(...)`/`build()` trả `Mono<ServerResponse>`. Không gọi `subscribe()` để tự “gửi response” hoặc `block()` để lấy ServerResponse trong reactive handler.

### 3.3. `RequestPredicate`

Predicate quyết định một request có phù hợp tuyến không:

~~~java
RequestPredicate predicate =
        RequestPredicates.GET("/api/books/{id}")
                .and(RequestPredicates.accept(
                        MediaType.APPLICATION_JSON));
~~~

Các factory phổ biến: `GET`, `POST`, `PUT`, `DELETE`, `path`, `accept`, `contentType`, `headers`, `queryParam` và `method`. Dùng `and`, `or`, `negate` để tạo điều kiện phức tạp; viết tests vì một predicate sai có thể khiến handler **không bao giờ được chọn**, không nhất thiết tạo đúng HTTP error status bạn mong muốn.

### 3.4. `RouterFunction`

Về mặt trừu tượng, router nhận `ServerRequest` và tìm handler phù hợp, kết quả là một publisher của handler hoặc empty khi không match. Ví dụ:

~~~java
RouterFunction<ServerResponse> health =
        RouterFunctions.route(
                RequestPredicates.GET("/api/health"),
                request -> ServerResponse.ok().bodyValue("OK"));
~~~

Đây là một router độc lập có thể hợp thành. Để Spring Boot phát hiện và đăng ký khi có auto-config WebFlux, bạn thường cung cấp một bean kiểu `RouterFunction<ServerResponse>`.

## 4. Router builder DSL: định nghĩa nhiều đường dẫn

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/api/books", handler::list)
                .GET("/api/books/{id}", handler::byId)
                .POST("/api/books", handler::create)
                .build();
~~~

`handler` là bean có các methods nhận `ServerRequest` và trả `Mono<ServerResponse>`. Builder method nhận HTTP method/path, optional extra predicate và handler; cuối cùng `build()` tạo router.

Ưu điểm:
- Route declaration tập trung, dễ review.
- Handler method có thể tách sang bean riêng; không phải annotate từng HTTP method.
- Có thể dùng DSL để nhóm common path/header/content-type conditions.
- Dễ composition với router đã được định nghĩa ở module khác.

### 4.1. Route order là một phần hợp đồng

**Sai** nếu `/{id}` đặt trước một static route:

~~~java
RouterFunctions.route()
        .GET("/api/books/{id}", handler::byId)
        .GET("/api/books/featured", handler::featured)
        .build();
~~~

`featured` có thể match `{id}` ở route đầu, khiến handler parse ID báo lỗi hoặc trả resource khác. **Đúng:**

~~~java
RouterFunctions.route()
        .GET("/api/books/featured", handler::featured)
        .GET("/api/books/{id}", handler::byId)
        .build();
~~~

Khác với annotated controller `@RequestMapping` có thuật toán so độ đặc hiệu giữa các mapping, functional router composition xét **trong thứ tự định nghĩa/hợp thành**. Nên đặt static/cụ thể trước variable/wildcards, và fallback/catch-all ở cuối.

## 5. `path(prefix, ...)` — nesting theo đường dẫn

Khi mọi books endpoints chung `/api/books`:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api/books", books -> books
                        .GET("/featured", handler::featured)
                        .GET("/{id}", handler::byId)
                        .GET("", handler::list)
                        .POST("", handler::create))
                .build();
~~~

`path("/api/books", builderConsumer)` là một cách **nesting path prefix**. Bên trong, `/{id}` chỉ là child path; HTTP client vẫn gọi `GET /api/books/3`, không gọi `/{id}`.

Trong code thực, một số examples của Spring dùng `GET(handler::list)` không khai báo child path cho danh sách. Nếu muốn route chỉ match collection root chứ không làm fallback quá rộng, có thể khai báo child path `""` và **test** `/api/books`, `/api/books/`, `/api/books/extra/path` theo Spring path-pattern rules bạn đang dùng. Không đoán mọi biến thể trailing slash đều tương đương.

### 5.1. Nest nhiều cấp prefix

~~~java
RouterFunctions.route()
        .path("/api", api -> api
                .path("/v1", v1 -> v1
                        .path("/books", books -> books
                                .GET("", handler::list)
                                .GET("/{id}", handler::byId))))
        .build();
~~~

Ví dụ trên tạo `GET /api/v1/books` và `GET /api/v1/books/{id}`. Mục đích là minh họa prefix nesting, không phải đề xuất cứ ba tầng path mới đúng. Quá nhiều cấp nesting có thể khiến full URL khó nhìn, khó debug và tăng rủi ro đặt filter sai phạm vi.

### 5.2. Builder `path` nhận cả Supplier router module

Spring WebFlux hỗ trợ một overload rất hữu ích:

~~~java
RouterFunctions.route()
        .path("/api/books", bookModule::routes)
        .path("/api/authors", authorModule::routes)
        .build();
~~~

`bookModule.routes()` và `authorModule.routes()` trả `RouterFunction<ServerResponse>` với các child routes tương đối. Đây là pattern **module composition**; application root config sở hữu public URL prefixes, còn feature modules sở hữu logic routing và handler.

## 6. `nest(predicate, ...)` — nesting theo điều kiện chung

Không phải mọi điều kiện chung đều là URL. Bạn có thể group theo `Accept`, `Content-Type`, request header hoặc custom predicate.

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api/books", b -> b
                        .nest(
                                RequestPredicates.accept(
                                        MediaType.APPLICATION_JSON),
                                json -> json
                                        .GET("/featured", handler::featured)
                                        .GET("/{id}", handler::byId)
                                        .GET("", handler::list))
                        .POST("",
                                RequestPredicates.contentType(
                                        MediaType.APPLICATION_JSON),
                                handler::create))
                .build();
~~~

Ý nghĩa:
- GET bên trong `nest(accept(JSON), ...)` chỉ match nếu client chấp nhận response JSON.
- POST ở **cấp builder books**, ngoài nhánh nested Accept nên không phải tuân theo Accept constraint của nhánh đó.
- POST có `contentType(JSON)`, kiểm định dạng **request body**, không phải Accept response.
- Route static `/featured` đứng trước variable `/{id}`.
- `GET("")` chọn collection root, `GET("/{id}")` chọn chi tiết theo matching path.
- Khi một nhánh không match, router tiếp tục thử route tiếp theo; không phải lập tức trả error JSON do bạn tự định nghĩa.

### 6.1. `path` và `nest(path(...))`

`path("/api/books", ...)` là DSL chuyên cho path prefix. `nest(RequestPredicates.path("/api/books"), ...)` cũng dùng predicate path để lồng router; `nest` còn nhận các điều kiện khác. Hãy dùng `path` cho tree theo resource và `nest` cho shared cross-cutting matching condition khi code dễ đọc hơn.

### 6.2. Kết hợp predicate

~~~java
RequestPredicate jsonVersionTwo =
        RequestPredicates.accept(MediaType.APPLICATION_JSON)
                .and(RequestPredicates.headers(
                        h -> "2".equals(
                                h.firstHeader("API-Version"))));
~~~

Nó chỉ chọn tuyến HTTP; không biến request header do client tự gửi thành quyền bảo mật hay quyền truy cập dữ liệu. Nếu có versioned API, định nghĩa rõ version parser, missing/unsupported values, default version và cache key. Không dùng cùng một route match quá rộng rồi âm thầm thay DTO không tương thích.

### 6.3. `queryParam` trong reactive package

~~~java
RequestPredicate summary =
        RequestPredicates.queryParam("mode", "summary");
~~~

Đây là **WebFlux.fn** `queryParam`, khác tên `param` thường thấy ở WebMvc.fn. Điều kiện này match `?mode=summary`; nếu thiếu/giá trị khác, route không match và có thể được xử lý bởi fallback nếu bạn khai báo.

## 7. Thứ tự route và fallback bên trong nhóm lồng nhau

Ví dụ rõ nhất là hai routes trùng path nhưng khác query:

~~~java
RouterFunctions.route()
        .GET("/api/books/featured",
                RequestPredicates.queryParam("mode", "summary"),
                handler::featuredSummary)
        .GET("/api/books/featured", handler::featuredHelp)
        .GET("/api/books/{id}", handler::byId)
        .build();
~~~

Khi có `?mode=summary`, chọn route đầu. Khi không có, route đầu không match nhưng route thứ hai có thể match; handler `featuredHelp` trả hướng dẫn lỗi 400. Vì `/{id}` đứng sau cả hai, `featured` không bị hiểu nhầm là một ID.

**Anti-pattern:** đặt `GET("/{id}")` ở đầu, hoặc đặt `GET("/**")` catch-all trước các routes cụ thể. Cái sai có thể âm thầm trả status 200 với body **không đúng handler**; chỉ kiểm status chưa đủ.

### 7.1. Routing fallback không thay validation

Nếu `GET /api/books/abc` match `/{id}`, predicate matching thành công. Khi handler không parse được `abc` thành số, đó là **validation error trong handler**, có thể trả 400. Không mặc định `{id}` chỉ nhận numeric.

### 7.2. Không được tùy tiện coi non-match là 400

Nếu `Accept: text/html` không match nested JSON route, kết quả có thể 404/406 tùy handler mapping, media type negotiation và error layer. Khi API contract yêu cầu 406 cụ thể, cần test và cấu hình lỗi rõ thay vì đoán Spring luôn tự map mọi predicate mismatch thành cùng status.

### 7.3. Context path và trailing slashes

`GET /api/books`, `GET /api/books/` và URL encoded segment khác nhau có thể không có cùng behavior theo Spring Framework path matching version/config. Test những URL được contract cho phép; đừng tự rewrite path bằng phép nối chuỗi đơn giản trong proxy rồi hy vọng tất cả nested paths vẫn đúng.

## 8. Hợp thành router bằng `and(...)` và `andRoute(...)`

Có thể xây router từng phần:

~~~java
RouterFunction<ServerResponse> first =
        RouterFunctions.route(
                RequestPredicates.GET("/api/health"),
                handler::health);

RouterFunction<ServerResponse> second =
        RouterFunctions.route(
                RequestPredicates.GET("/api/status"),
                handler::status);

RouterFunction<ServerResponse> combined = first.and(second);
~~~

Khi request match router đầu, router đó cung cấp handler; nếu không, chuyển sang router sau. `and(...)` giữ tính modular mà không bắt buộc dùng builder. `andRoute(...)` tiện khi nối một predicate/handler:

~~~java
RouterFunction<ServerResponse> combined =
        first.andRoute(
                RequestPredicates.GET("/api/status"),
                handler::status);
~~~

Đây là fragments cần `handler` định nghĩa riêng. Không tự suy rằng `and` chạy **cả hai handlers** hoặc thực hiện cả hai side effects. Nó tạo một logic **chọn một handler phù hợp**.

### 8.1. Hợp thành qua Builder `add(...)`

~~~java
RouterFunction<ServerResponse> finalRouter =
        RouterFunctions.route()
                .GET("/api/health", handler::health)
                .add(bookRouter)
                .add(authorRouter)
                .build();
~~~

`bookRouter` và `authorRouter` đã có từ module khác. Nếu các module tự sở hữu absolute paths, `add` hữu ích. Nếu muốn **root config sở hữu prefixes**, dùng `path("/api/books", bookModule::routes)` như ví dụ runnable. Đừng cùng lúc prefix ở module và bên ngoài làm URL thành `/api/books/api/books`.

### 8.2. Hợp thành với `RouterFunctions.nest(...)` tĩnh

~~~java
RouterFunction<ServerResponse> child =
        RouterFunctions.route()
                .GET("/{id}", handler::byId)
                .build();

RouterFunction<ServerResponse> nested =
        RouterFunctions.nest(
                RequestPredicates.path("/api/books"), child);
~~~

Đây là một phiên bản khác của nesting, hữu ích khi child router đã được dựng sẵn. Nó vẫn tuân theo quy tắc path matching và order của router con; không thêm round trip, HTTP redirect hay Spring bean mới cho mỗi request.

## 9. Tổ chức tuyến theo tính năng (feature-oriented routing)

### 9.1. Thiết kế thư mục

~~~text
com.example.catalog
├── CatalogApplication.java
├── config/
│   └── ApiRoutesConfiguration.java    # composition root
├── books/
│   ├── Book.java
│   ├── CreateBook.java
│   ├── BookStore.java
│   ├── BookHandler.java
│   └── BookRoutes.java                # child router
├── authors/
│   ├── AuthorHandler.java
│   └── AuthorRoutes.java
└── health/
    └── HealthHandler.java
~~~

**Một feature sở hữu** DTO/validation/handlers/routing, application root sở hữu URL prefix và thứ tự giữa các modules. Service/domain không phụ thuộc trực tiếp vào HTTP routing nếu hệ thống lớn; ví dụ demo gom những thứ đơn giản cho dễ chạy.

### 9.2. So với một router toàn cục

| Router toàn cục rất lớn | Feature-oriented routers |
| --- | --- |
| Dễ tìm mọi route ở một file ban đầu | Routes và handler gần cùng feature |
| Prefix và Accept có thể lặp | Prefix/conditions có thể group tại một nơi |
| Conflict khó review khi API lớn | Ownership mỗi nhóm rõ ràng |
| Một thay đổi có thể gây merge conflicts | Team làm việc song song theo module |
| Có nguy cơ một catch-all che mọi nhóm | Composition root kiểm soát thứ tự |
| Cấu hình filters có thể lan sang toàn API | Có thể áp filter đúng phạm vi |
| Dễ khi dự án rất nhỏ | Tốt khi nhiều bounded contexts |

Không tách 20 classes cho một API chỉ có một route. Dùng feature modules khi chúng **giảm coupling, lặp và xung đột** chứ không phải để chạy theo một chuẩn folder layout máy móc.

### 9.3. Ownership phải nhất quán

Chọn một trong hai cách:
1. **Module sở hữu absolute path** (`/api/books/...`) và root ghép bằng `and/add`.
2. **Root sở hữu prefix** (`/api/books`), module chỉ định child paths (`""`, `/{id}`, `/featured`) rồi root dùng `path(prefix, supplier)`.

Ví dụ bên dưới dùng **cách 2**. Không kết hợp vô ý cả hai, không copy prefix vào module và composition root cùng lúc.

### 9.4. Bean lifecycle và registration

Trong Boot WebFlux, một `RouterFunction<ServerResponse>` **bean** được tìm bởi routing infrastructure. Nếu chỉ tạo một RouterFunction local bên trong method nhưng không đăng ký hoặc gắn vào một bean hợp thành, route có thể không tồn tại ở runtime.

Bài demo dùng **một bean duy nhất `apiRoutes`** ở composition root. `BookRoutes` và `AuthorRoutes` là Spring components có method `routes()` trả router con, **không** đăng ký mỗi router con như một RouterFunction bean độc lập; nhờ vậy không có bản route child path `/{id}` lọt ra ngoài global prefix.

## 10. Bộ lọc `before`, `after` và `filter` theo phạm vi

Functional WebFlux cho phép filter trên router function/builder:
- `before(Function<ServerRequest,ServerRequest>)`: biến đổi request trước handler.
- `after(BiFunction<ServerRequest,ServerResponse,ServerResponse>)`: xử lý response object sau handler.
- `filter(HandlerFilterFunction<ServerResponse,ServerResponse>)`: bao quanh invocation và gọi `next.handle(request)`.
- `onError(...)`: biến exception thành `Mono<ServerResponse>` phù hợp theo API reactive.

Ví dụ conceptual fragment:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api/books", books -> books
                        .GET("/{id}", handler::byId)
                        .before(req -> ServerRequest.from(req)
                                .header("X-Route-Scope", "books")
                                .build()))
                .after((req, response) -> response)
                .build();
~~~

`before` nằm ở nhánh books sẽ áp cho routes trong nhánh đó; `after` nằm ở builder ngoài áp cho những routes được builder xây, bao gồm routes con. Đừng dùng headers nhân tạo như `X-Route-Scope` làm permission/identity; nó chỉ minh họa cách builder scope hoạt động.

### 10.1. `filter` và error propagation

~~~java
.filter((request, next) ->
        next.handle(request)
                .doOnError(error -> {
                    // Chỉ log metadata phù hợp chính sách, không log token/body.
                }))
~~~

Filter reactive có thể quan sát hoặc biến đổi publisher, nhưng **không nên gọi `block()`**. Một filter không gọi `next.handle(request)` có thể chủ động trả alternate response, phù hợp rate limits/feature gates khi thiết kế kỹ, nhưng **không thay** Spring Security.

### 10.2. Security và request matching

Routing predicates quyết định **handler**, không quyết định **user có quyền**. Spring Security WebFlux dùng `SecurityWebFilterChain` và `ServerHttpSecurity`, thường xử lý security trước functional handlers. Với sách thuộc tenant, kiểm ownership/tenant ở service hoặc auth layer dù route match đúng `/api/books/{id}`.

Router filter custom không tự có CSRF/session/cookie security. Nếu frontend cross-origin, cần CorsWebFilter và preflight phối hợp đúng security; hãy cấu hình theo chuẩn WebFlux, không copy `HttpSecurity` của Servlet MVC.

### 10.3. `onError` không bắt mọi lỗi toàn stack

Một `onError` trong router có thể xử lý exceptions của handler/filter thuộc phạm vi router. Lỗi ở gateway, proxy, security filters trước router hoặc response đã commit có thể cần error mechanisms riêng. Với JSON error contract ổn định, nên có common error model/handlers và integration tests; đừng catch `Throwable` bừa bãi rồi trả HTTP 200.

### 10.4. Phạm vi filter theo nested group

Nếu chỉ muốn biến đổi các GET JSON của Books, gắn filter vào builder **bên trong `nest(accept(JSON), ...)`**. Nếu muốn mọi Books route kể cả POST, gắn lên **BookRoutes builder**. Nếu muốn cả Books và Authors, gắn ở **apiRoutes composition builder**.

Sơ đồ:

~~~text
API builder-level filter
|
+-- /health
+-- /books    <- Books builder-level filter
|    |
|    +-- nest(accept(JSON)) <- GET JSON-only filter
|    |     +-- /featured
|    |     +-- /{id}
|    |     +-- collection list
|    +-- POST
|
+-- /authors  <- Authors builder-level filter
~~~

Luôn kiểm thứ tự và phạm vi filter bằng tests (header/trace logging) khi thêm nhiều modules. Đừng dùng wildcard filter scope rồi vô tình áp audit/payload logging vào endpoint login hoặc dữ liệu nhạy cảm.

## 11. Ví dụ chạy được: Java 17 / Spring Boot 3.3.5 / WebFlux.fn

Ta tạo một ứng dụng với:
- `GET /api/health` trả plain text `OK`.
- `GET /api/books` trả danh sách JSON.
- `GET /api/books/featured?mode=summary` trả sách nổi bật.
- `GET /api/books/featured` thiếu tham số trả 400 với error code xác định, **không lọt vào `/{id}`**.
- `GET /api/books/{id}` trả sách hoặc 404; ID sai format trả 400.
- `POST /api/books` nhận JSON và tạo sách, trả 201 + Location; title trống trả 400.
- `GET /api/authors` và `GET /api/authors/{id}` được khai báo ở feature router độc lập.
- Một `@Bean RouterFunction<ServerResponse> apiRoutes` duy nhất hợp thành ba modules.

Ví dụ sử dụng in-memory store, không có authentication/database. Dù in-memory data được tạo an toàn trên một JVM, nó **không** chia sẻ giữa nhiều instances/pods và không thay repository production. HTTP tests xác minh behavior mà không dựa vào thứ tự test.

~~~text
webflux-feature-router/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/catalog/
    │   ├── CatalogApplication.java
    │   ├── config/ApiRoutesConfiguration.java
    │   ├── books/
    │   │   ├── Book.java
    │   │   ├── CreateBook.java
    │   │   ├── BookStore.java
    │   │   ├── BookHandler.java
    │   │   └── BookRoutes.java
    │   ├── authors/
    │   │   ├── AuthorHandler.java
    │   │   └── AuthorRoutes.java
    │   └── health/HealthHandler.java
    └── test/java/com/example/catalog/
        └── FeatureRouterIntegrationTest.java
~~~

### 11.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-feature-router'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không thêm Spring MVC starter. Spring Boot quản lý phiên bản Spring WebFlux và Reactor tương thích. Cần Gradle wrapper tương thích Java 17/Boot 3.3.5 khi chạy các lệnh `./gradlew`.

### 11.2. Main application

`src/main/java/com/example/catalog/CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### 11.3. Book domain types

`src/main/java/com/example/catalog/books/Book.java`:

~~~java
package com.example.catalog.books;

public record Book(long id, String title) {}
~~~

`src/main/java/com/example/catalog/books/CreateBook.java`:

~~~java
package com.example.catalog.books;

public record CreateBook(String title) {}
~~~

Record DTOs dùng Java 17. Khi deserialize JSON `{"title":"Reactive Routing"}`, Jackson hỗ trợ canonical record constructors theo starter WebFlux. Ví dụ validate title trong handler; production nên áp schema/Bean Validation, độ dài/tập ký tự, authorization và request-size limit.

### 11.4. BookStore: repository giả lập thread-safe

`src/main/java/com/example/catalog/books/BookStore.java`:

~~~java
package com.example.catalog.books;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class BookStore {

    private final ConcurrentMap<Long, Book> books =
            new ConcurrentHashMap<>();

    private final AtomicLong sequence = new AtomicLong(2);

    public BookStore() {
        books.put(1L, new Book(1L, "Spring WebFlux"));
        books.put(2L, new Book(2L, "Reactor Patterns"));
    }

    public Flux<Book> all() {
        return Flux.defer(() -> Flux.fromIterable(
                books.values().stream()
                        .sorted(Comparator.comparingLong(Book::id))
                        .toList()));
    }

    public Mono<Book> find(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(books.get(id)));
    }

    public Mono<Book> create(String title) {
        return Mono.fromSupplier(() -> {
            long id = sequence.incrementAndGet();
            Book book = new Book(id, title);
            books.put(id, book);
            return book;
        });
    }
}
~~~

**Lưu ý về tính reactive:** `ConcurrentHashMap` chỉ dùng bộ nhớ local và thao tác rất nhanh; `Mono.defer/fromSupplier` khiến việc đọc/ghi diễn ra khi subscription, nhưng **không tự làm blocking database calls non-blocking**. Không thay `books.get(id)` bằng JDBC `jdbcTemplate.queryForObject` trong lambda rồi để nó chạy trên event loop. Nếu dùng JDBC legacy, isolate qua `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`; nếu cần reactive DB end-to-end, cân nhắc R2DBC đúng driver/transaction stack.

### 11.5. BookHandler

`src/main/java/com/example/catalog/books/BookHandler.java`:

~~~java
package com.example.catalog.books;

import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class BookHandler {

    public record ApiError(String code, String message) {}

    private final BookStore store;

    public BookHandler(BookStore store) {
        this.store = store;
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.all(), Book.class);
    }

    public Mono<ServerResponse> featured(ServerRequest request) {
        return store.find(1L)
                .flatMap(book -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> featuredHelp(ServerRequest request) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiError(
                        "FEATURED_MODE_REQUIRED",
                        "Use mode=summary"));
    }

    public Mono<ServerResponse> byId(ServerRequest request) {
        String raw = request.pathVariable("id");
        long id;

        try {
            id = Long.parseLong(raw);
        } catch (NumberFormatException ex) {
            return invalidId();
        }

        if (id <= 0) {
            return invalidId();
        }

        return store.find(id)
                .flatMap(book -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    private Mono<ServerResponse> invalidId() {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiError(
                        "INVALID_BOOK_ID", "id must be a positive integer"));
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateBook.class)
                .flatMap(input -> {
                    if (input.title() == null
                            || input.title().isBlank()
                            || input.title().length() > 100) {
                        return ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new ApiError(
                                        "INVALID_BOOK_TITLE",
                                        "title is required and max 100 chars"));
                    }

                    return store.create(input.title().trim())
                            .flatMap(book ->
                                    ServerResponse.created(
                                            URI.create("/api/books/" + book.id()))
                                            .contentType(MediaType.APPLICATION_JSON)
                                            .bodyValue(book));
                })
                .switchIfEmpty(ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(new ApiError(
                                "MISSING_BODY", "JSON body is required")));
    }
}
~~~

Điểm quan trọng:
- Tất cả handler methods trả `Mono<ServerResponse>` (hoặc `Mono` từ body publisher), không dùng Servlet `ServerResponse` sync.
- `ServerResponse.ok().body(store.all(), Book.class)` cho phép framework stream/encode `Flux<Book>` theo JSON codec; đây là array response cho use case thông thường với Jackson/WebFlux.
- Trong `create`, **chỉ subscribe khi HTTP framework xử lý request**; không gọi `request.bodyToMono(...).block()`.
- Bad ID được map 400, missing book được map 404, thiếu `mode=summary` được map 400 có mã ổn định.
- Demo không làm authentication/tenant authorization. Trước khi trả Book thật, service production phải kiểm principal và quyền đối với resource.

### 11.6. BookRoutes: child paths không có `/api/books`

`src/main/java/com/example/catalog/books/BookRoutes.java`:

~~~java
package com.example.catalog.books;

import static org.springframework.web.reactive.function.server.RequestPredicates.accept;
import static org.springframework.web.reactive.function.server.RequestPredicates.contentType;
import static org.springframework.web.reactive.function.server.RequestPredicates.queryParam;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Component
public class BookRoutes {

    private final BookHandler handler;

    public BookRoutes(BookHandler handler) {
        this.handler = handler;
    }

    public RouterFunction<ServerResponse> routes() {
        return RouterFunctions.route()
                .nest(accept(MediaType.APPLICATION_JSON), json -> json
                        .GET("/featured",
                                queryParam("mode", "summary"),
                                handler::featured)
                        .GET("/featured", handler::featuredHelp)
                        .GET("/{id}", handler::byId)
                        .GET("", handler::list))
                .POST("", contentType(MediaType.APPLICATION_JSON),
                        handler::create)
                .build();
    }
}
~~~

Đây là một **router con**, nên không có `/api/books` trong các paths. Nó được bọc ở composition root bằng `path("/books", bookRoutes::routes)` trong nhánh `path("/api", ...)`.

**Order có chủ đích:**
1. Featured có query param `mode=summary` là tuyến cụ thể nhất.
2. Featured fallback không có mode đứng sau.
3. Variable route `/{id}` đứng sau static `/featured`.
4. Collection route `GET("")` đứng sau các GET khác.
5. POST có `contentType(JSON)` nhưng **không nằm trong nest Accept(JSON)** vì Accept và Content-Type có vai trò khác.

Nếu bạn đổi thứ tự để `/{id}` đứng đầu, `GET /api/books/featured` có thể vào `byId`, khiến API error code khác. WebTestClient bên dưới kiểm chính xác error message để phát hiện regression này.

### 11.7. AuthorHandler: feature độc lập

`src/main/java/com/example/catalog/authors/AuthorHandler.java`:

~~~java
package com.example.catalog.authors;

import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class AuthorHandler {

    public record Author(long id, String name) {}

    private static final List<Author> AUTHORS =
            List.of(new Author(1L, "An"),
                    new Author(2L, "Binh"));

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(AUTHORS);
    }

    public Mono<ServerResponse> byId(ServerRequest request) {
        String id = request.pathVariable("id");

        return AUTHORS.stream()
                .filter(author ->
                        Long.toString(author.id()).equals(id))
                .findFirst()
                .map(author -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(author))
                .orElseGet(() -> ServerResponse.notFound().build());
    }
}
~~~

Ở đây `byId` so sánh path variable với ID dạng string; input không đúng định dạng trả 404, khác với Book handler có policy 400. Đây là minh họa **để bạn nhận ra policies theo feature cần thống nhất khi phát hành API chung**. Nếu muốn error contracts đồng nhất, dùng common validation/error model và tests. Danh sách authors là in-memory fixture, không DB.

### 11.8. AuthorRoutes: router con đơn giản

`src/main/java/com/example/catalog/authors/AuthorRoutes.java`:

~~~java
package com.example.catalog.authors;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Component
public class AuthorRoutes {

    private final AuthorHandler handler;

    public AuthorRoutes(AuthorHandler handler) {
        this.handler = handler;
    }

    public RouterFunction<ServerResponse> routes() {
        return RouterFunctions.route()
                .GET("/{id}", handler::byId)
                .GET("", handler::list)
                .build();
    }
}
~~~

Không dùng bean `RouterFunction` ở module này: chỉ có `@Component AuthorRoutes` và method trả router khi root composer gọi.

### 11.9. HealthHandler: tách cơ chế vận hành

`src/main/java/com/example/catalog/health/HealthHandler.java`:

~~~java
package com.example.catalog.health;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class HealthHandler {

    public Mono<ServerResponse> health(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("OK");
    }
}
~~~

Demo `/api/health` không gọi network/JDBC. Với production liveness/readiness, cân nhắc Spring Boot Actuator `/actuator/health`, Kubernetes probes và security policy phù hợp; đừng nhầm một response “OK” với hệ thống đủ sẵn sàng cho tất cả dependency calls.

### 11.10. Composition root — lớp quyết định URL public

`src/main/java/com/example/catalog/config/ApiRoutesConfiguration.java`:

~~~java
package com.example.catalog.config;

import com.example.catalog.authors.AuthorRoutes;
import com.example.catalog.books.BookRoutes;
import com.example.catalog.health.HealthHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class ApiRoutesConfiguration {

    @Bean
    RouterFunction<ServerResponse> apiRoutes(
            BookRoutes books, AuthorRoutes authors,
            HealthHandler health) {

        return RouterFunctions.route()
                .path("/api", api -> api
                        .GET("/health", health::health)
                        .path("/books", books::routes)
                        .path("/authors", authors::routes))
                .build();
    }
}
~~~

**Vì sao đây là composition root:**
- Chỉ một `@Bean RouterFunction<ServerResponse>` được công bố cho WebFlux routing infrastructure.
- Prefix `/api` bao trùm API; `/books` và `/authors` được định nghĩa ở đây, không trong child module.
- `BookRoutes` và `AuthorRoutes` vẫn là Spring-managed components để nhận dependency injection, nhưng methods `routes()` không bị tự đăng ký như top-level router beans.
- `/api/health` là route riêng, không bị `accept(JSON)` của Books ảnh hưởng.
- Cây router dễ đọc khi review; thứ tự compose ở đây có ý nghĩa nếu các child routers có overlapping/catch-all paths.

Nếu muốn thêm `/api/v2/books`, có thể compose một BookRoutesV2 dưới một prefix mới và giữ v1. Không tự tái sử dụng một module không tương thích DTO rồi nghĩ chỉ thêm `/v2` là đủ để version API.

## 12. WebTestClient kiểm chứng nesting, order và module boundaries

`WebTestClient` phù hợp cho reactive Spring WebFlux. Chúng ta dùng embedded server trên port ngẫu nhiên để kiểm thực sự HTTP routing/body/status. Không dùng Servlet `MockMvc` như thể chúng là cùng programming model.

`src/test/java/com/example/catalog/FeatureRouterIntegrationTest.java`:

~~~java
package com.example.catalog;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FeatureRouterIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void healthIsIndependentFromBooksJsonCondition() {
        client.get().uri("/api/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void bookCollectionIsUnderNestedPrefix() {
        client.get().uri("/api/books")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$[0].id").isEqualTo(1)
                .jsonPath("$[1].id").isEqualTo(2);
    }

    @Test
    void bookDetailMatchesVariableRoute() {
        client.get().uri("/api/books/2")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Reactor Patterns");
    }

    @Test
    void featuredQueryPredicateBeatsFallback() {
        client.get().uri("/api/books/featured?mode=summary")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(1);
    }

    @Test
    void featuredWithoutModeDoesNotHitIdHandler() {
        client.get().uri("/api/books/featured")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("FEATURED_MODE_REQUIRED")
                .jsonPath("$.message")
                    .isEqualTo("Use mode=summary");
    }

    @Test
    void invalidIdHasExplicitBusinessError() {
        client.get().uri("/api/books/abc")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_BOOK_ID");
    }

    @Test
    void missingBookReturnsNotFound() {
        client.get().uri("/api/books/9999")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void postBookCreatesResourceWithLocation() {
        client.post().uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("title", "Reactive Routing"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().valueMatches(
                        HttpHeaders.LOCATION, "/api/books/[0-9]+")
                .expectBody()
                .jsonPath("$.title").isEqualTo("Reactive Routing");
    }

    @Test
    void blankBookTitleReturns400() {
        client.post().uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("title", "   "))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_BOOK_TITLE");
    }

    @Test
    void authorListIsIndependentModule() {
        client.get().uri("/api/authors")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$[0].name").isEqualTo("An")
                .jsonPath("$[1].name").isEqualTo("Binh");
    }

    @Test
    void authorDetailIsNestedUnderAuthors() {
        client.get().uri("/api/authors/1")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("An");
    }
}
~~~

### 12.1. Vì sao phải assert JSON chứ không chỉ status?

Nếu `GET("/{id}")` được chuyển lên trước `GET("/featured")`, URL `featured` có thể vào handler ID và trả **400**. Nếu test chỉ assert `status().isBadRequest()`, nó vẫn pass dù route sai. Vì vậy test kiểm cả `code=FEATURED_MODE_REQUIRED` và message; đây là **contract test cho thứ tự route**.

### 12.2. Vì sao tests không phụ thuộc thứ tự execution?

BookStore mặc định có ID 1 và 2, cả hai không bị delete. POST test tạo thêm sách với AtomicLong nhưng không assert fixed ID 3. Tests cho initial IDs kiểm hai phần tử đầu được sort tăng dần, nên vẫn ổn ngay cả khi POST chạy trước. Nếu thêm delete/mutate fixtures hoặc nhiều test instances, nên reset repository theo test hoặc khởi tạo context độc lập.

### 12.3. Thử negative Accept trong integration tests

Một bài tập mở rộng là gửi `Accept: text/html` đến `GET /api/books/1` để xác nhận **nhánh nested JSON không match**. HTTP status cuối có thể khác tùy handler mappings/global error handling, vì thế không hard-code một status chưa xác minh. Test có thể bắt đầu bằng assertion rằng response **không** phải 200 với JSON Book, rồi khi có policy rõ, chốt exact status/error contract.

### 12.4. Chạy tests

Trong project có Gradle wrapper đã tạo tương thích Java 17:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

Tài liệu nguồn mô tả mọi class/code files, nhưng không kèm scripts của Gradle wrapper. Nếu chưa có wrapper, tạo từ Gradle installation phù hợp; `build.gradle` không tự sinh `gradlew`. Không có database migration hay external APIs, nên output HTTP deterministic ngoại trừ ID tạo mới theo trạng thái process.

## 13. Chạy với curl

### 13.1. Health

~~~bash
curl -i 'http://localhost:8080/api/health'
~~~

Dự kiến HTTP 200, Content-Type text/plain, body:

~~~text
OK
~~~

### 13.2. Books collection và details

~~~bash
curl -i 'http://localhost:8080/api/books' \
  -H 'Accept: application/json'

curl -i 'http://localhost:8080/api/books/2' \
  -H 'Accept: application/json'
~~~

Danh sách ban đầu:

~~~json
[
  {"id":1,"title":"Spring WebFlux"},
  {"id":2,"title":"Reactor Patterns"}
]
~~~

Chi tiết ID 2:

~~~json
{"id":2,"title":"Reactor Patterns"}
~~~

JSON response thực tế có thể một dòng; đây là phiên bản dễ đọc. Controller/handler có thể trả 404 nếu ID không tồn tại, không tự ép mọi query thành 200.

### 13.3. Featured đúng query và fallback

~~~bash
curl -i 'http://localhost:8080/api/books/featured?mode=summary' \
  -H 'Accept: application/json'

curl -i 'http://localhost:8080/api/books/featured' \
  -H 'Accept: application/json'
~~~

Với `mode=summary`, response JSON sách ID 1. Không có mode, response 400:

~~~json
{"code":"FEATURED_MODE_REQUIRED","message":"Use mode=summary"}
~~~

Đây là bằng chứng nhóm static routes đã được chọn trước variable `/{id}`.

### 13.4. Tạo sách

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Functional WebFlux"}'
~~~

Dự kiến HTTP 201, `Location: /api/books/3` trên JVM mới chưa có POST nào, cùng JSON:

~~~json
{"id":3,"title":"Functional WebFlux"}
~~~

ID sẽ thay đổi nếu có POST trước đó; không đặt fixed ID vào client business logic. Endpoint demo dùng in-memory store và không có auth; production cần DB/validation/authorization/idempotency phù hợp.

### 13.5. Author routes

~~~bash
curl -i 'http://localhost:8080/api/authors'
curl -i 'http://localhost:8080/api/authors/1'
~~~

Ban đầu authors list:

~~~json
[
  {"id":1,"name":"An"},
  {"id":2,"name":"Binh"}
]
~~~

Chi tiết:

~~~json
{"id":1,"name":"An"}
~~~

Phần này chứng minh **AuthorRoutes** và **BookRoutes** có thể được compose dưới cùng `/api` mà không phải chung một handler class.

## 14. Hợp thành qua nhiều bean RouterFunction: nên và không nên

Trong Spring Boot WebFlux có thể khai báo nhiều beans `RouterFunction<ServerResponse>`, framework sẽ thu thập/ghép route theo infrastructure. Tuy vậy, nếu các routers có overlapping paths, việc dựa vào registration order không tường minh có thể làm API biến động khi refactor.

**Khuyến nghị thực dụng:** với hệ thống có nhiều module và path prefix chung, dùng một bean composition root như ví dụ; thứ tự được viết rõ trong code và có integration tests. Nếu cố ý dùng nhiều top-level RouterFunction beans, tài liệu hóa `@Order`/ordering semantics đúng version framework, thêm conflict detection/tests và giữ quyền sở hữu paths rõ ràng.

Một lỗi dễ gặp: child module đã tạo bean route `GET("/{id}")` nhưng root lại compose nó dưới `/api/books`; route relative `/{id}` có thể được framework đăng ký ngoài prefix khi bean tồn tại độc lập. Nếu module chỉ cung cấp child routes để root compose, **đừng đánh dấu child RouterFunction là `@Bean` riêng**.

### 14.1. Versioning qua root composer

Hai phiên bản API có thể dùng modules riêng:

~~~java
RouterFunctions.route()
        .path("/api/v1/books", v1BookRoutes::routes)
        .path("/api/v2/books", v2BookRoutes::routes)
        .build();
~~~

Fragment này cần hai components. Một số dự án có thể dùng header/query/media type versioning; với Spring Framework 7 có version-specific routing infrastructure mới hơn. **Đừng dùng `RequestPredicates.version(...)` theo tài liệu Spring 7 trong Spring Boot 3.3.x**, trừ khi bạn nâng cả platform tương thích.

### 14.2. Giữ business logic dùng chung khi hợp lý

Router v1/v2 có thể dùng shared domain service nhưng DTO adapters khác nhau. Không expose persistence entities trực tiếp ra mọi API versions; một refactor entity có thể vô tình phá cả v1. Nếu business semantics khác thật, cần policy rõ thay vì chỉ đổi name của router.

## 15. CORS, authentication và errors với nhiều feature routers

### 15.1. CORS cho WebFlux functional endpoints

Spring WebFlux.fn sử dụng CORS infrastructure thường qua `CorsWebFilter` khi cần global/functional routing. CORS policy không tự được tạo bởi `path("/api", ...)` hay `nest(accept(JSON), ...)`. Browser POST JSON cross-origin thường preflight; cần allow đúng Origin/Methods/Headers và phối hợp với Spring Security reactive.

**Không dùng `Access-Control-Allow-Origin: *` cùng credentialed browser requests.** Với cookie authentication phải xét `SameSite`, `Secure`, CSRF protection và thực tế third-party cookies. CORS không chứng minh user được cấp quyền.

### 15.2. Spring Security filter chain

Các tuyến functional WebFlux vẫn đi qua reactive `SecurityWebFilterChain` nếu dependency/config được bật. Có thể phân policy:
- `/api/health` public theo threat model.
- `/api/books/**` authenticated, POST cần write permission.
- `/api/authors/**` read policy độc lập.
- Mọi route ngoài allowlist deny by default.

Đây chỉ là design guideline; demo không kèm security config nên các endpoints có thể gọi công khai. Đừng vận hành production với data private theo mô hình demo mà thiếu auth.

### 15.3. Lỗi và `ProblemDetail`

Router không match là một loại lỗi routing; handler ném exception là loại khác; security layer 401/403 có thể xảy ra trước handler. Nếu sản phẩm muốn một JSON schema như RFC 9457 `ProblemDetail` với `code` ổn định, thiết kế common error handling cho đúng từng layer và test 400/401/403/404/405/406/415/500. Tránh bắt `Throwable` rồi trả 200 vì đã “chuẩn hóa” body.

### 15.4. Filter and auditing

Router-level filter có thể gắn X-Trace-Id, đo latency, audit module. Tuy nhiên:
- Không log body/Authorization/Cookie/tokens.
- Không dùng raw unbounded headers để đặt metric label.
- Không dùng request ThreadLocal để giữ security context trong Reactor pipelines có thể đổi scheduler.
- Nếu cần tracing, dùng Reactor Context và integrations tương thích (Micrometer/Spring Security).
- Lỗi response đã commit có thể không đổi status/headers được như trước commit.

## 16. Routing functional và annotated controllers có thể cùng tồn tại

Spring WebFlux hỗ trợ cả annotated controllers và functional routes. Nên tránh:
- Cùng `GET /api/books/{id}` được đăng ký ở hai mô hình.
- Một global catch-all RouterFunction vô tình che static resources và annotated endpoints.
- Dùng error formatter ở annotated controller nhưng quên functional handler.
- Dùng `@Valid @RequestBody` expectations khi functional handler chỉ gọi `bodyToMono` không có validator.
- Dựa vào thứ tự mapping của Spring WebFlux infrastructure mà không có test.

Trong codebase lớn, thống nhất **ownership cho mỗi URL/method** và quy tắc chuyển API sang mô hình mới. Không refactor hàng loạt sang RouterFunction chỉ vì syntax trông ngắn hơn; nếu annotations đang hoạt động tốt và có OpenAPI tooling phù hợp thì có thể giữ chúng.

## 17. Hiệu năng và reactive stream không bị thay đổi vì nesting

Nesting/hợp thành routers chủ yếu là chuyện **matching/declaration**, không phải kỹ thuật tăng tốc network I/O. Một số hiểu nhầm:

| Hiểu nhầm | Thực tế |
| --- | --- |
| "RouterFunction tự làm JDBC non-blocking" | Không; JDBC có thể chặn event loop, cần offload hoặc reactive driver |
| "Nesting tạo thread pool riêng" | Không; chỉ tổ chức match predicates |
| "Mỗi feature có RouterFunction thì độc lập resource quota" | Không; vẫn có thể chia sẻ Netty loops/schedulers/DB pool |
| "and() chạy song song các handlers" | Không; nó chọn handler đầu tiên match |
| "Flux đã có backpressure nên database không thể quá tải" | Cần concurrency/connection-pool budgets, bounded buffers và admission |
| "before/after filters sẽ tự bảo mật mọi route" | Không; SecurityWebFilterChain/domain auth độc lập |
| "Một request chạy cả module A và module B" | Thường chỉ một route handler được chọn nếu match |
| "Router order không quan trọng vì Spring chọn pattern cụ thể" | Thứ tự trong functional composition rất quan trọng |

Nếu feature gọi service blocking từ handler, dùng Reactor `Mono.fromCallable(...).subscribeOn(boundedElastic)` hoặc dedicated worker pool theo dependency load. Với WebClient/R2DBC non-blocking, return publishers và tránh `block()`. Đo p95/p99, Netty event-loop starvation, connection pool, memory pressure và error rates thay vì giả định tổ chức router sẽ tự cải thiện throughput.

## 18. Troubleshooting: sai route và sai module ownership

| Triệu chứng | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| `RouterFunction` không được nhận | Nhầm package WebMvc.fn hoặc không đăng ký bean | Dùng reactive package và composition bean |
| `GET /api/books` 404 | Nested prefix/child path sai | Vẽ full URL từng path cấp |
| `/api/books/featured` vào ID handler | `/{id}` đứng trước static route | Đặt static trước và assert error code |
| `GET /api/books` trả dữ liệu Authors | Compose router rộng/catch-all sai | Ownership/prefixes tường minh |
| `path("/api/books", ...)` tạo double prefix | Module cũng khai báo `/api/books` | Module child paths tương đối |
| `GET /api/books/1` trả không match khi Accept text/html | `nest(accept(JSON))` áp lên GET | Kiểm client Accept, policy 406 |
| POST body JSON bị 415 | Content-Type sai hoặc decoder không hỗ trợ | Kiểm `contentType(JSON)` và codecs |
| Query `mode=summary` không được nhận | Import nhầm `param` hoặc thiếu query | Dùng reactive `queryParam` |
| `@Bean` child routes chạy ngoài prefix | Đăng ký router con riêng ngoài composition | Chỉ root bean khi dùng relative routers |
| Filter GET áp nhầm POST | Filter đặt ở builder cha thay vì nested GET group | Chuyển vào đúng `nest` scope |
| Security policy chỉ bảo vệ annotations | Request matchers chưa phủ functional URL | Kiểm SecurityWebFilterChain với WebTestClient |
| CORS preflight bị 401 | Auth xử lý OPTIONS trước CORS | Config CorsWebFilter/Security đúng |
| Errors khác giữa modules | Mỗi handler tự thiết kế status/body | Common error contract và tests |
| GET byId với "abc" trả status khó đoán | Không validate path variable | Parse/validate và typed 400 |
| Dữ liệu test tăng ID tùy thứ tự | Shared mutable in-memory store | Test isolation, không assert absolute next ID |
| 2 RouterFunction beans có conflict | Không rõ registration order | Single composition root hoặc @Order có test |
| Spring Boot chạy MVC | Lẫn `starter-web` với WebFlux starter | Chọn platform đúng |
| WebFlux handler gọi `block()` | Nhầm reactive type với non-blocking | Return publishers, offload blocking legacy |
| HTTP 200 nhưng payload sai | Route đầu match nhầm handler | Assert body/schema/error code/headers |
| OpenAPI không thấy functional route | Tool chỉ đọc annotation mapping | Explicit OpenAPI registration/annotations phù hợp |

### Quy trình debug

1. Xác minh Gradle dependencies và imports thuộc **WebFlux.fn**.
2. Kiểm chỉ những RouterFunction beans mong đợi được register.
3. Vẽ route tree của composition root cùng child paths tương đối.
4. Rà route order trong từng module: static → constrained → variable → fallback.
5. Ghi method, full path, query, Accept, Content-Type, headers — không log secrets.
6. Kiểm nest predicates và filter scope theo tầng.
7. Phân biệt route non-match, handler validation error và security filter error.
8. Kiểm bodyToMono/codec và response type `Mono<ServerResponse>`, không block.
9. Chạy WebTestClient success/negative tests có assertions đúng handler/schema.
10. Nếu có gateway/CDN/rewrite, kiểm HTTP thực end-to-end sau embedded integration tests.

## 19. Checklist thiết kế module router

- [ ] Root owns public prefixes hoặc modules own full paths — chọn một nhất quán.
- [ ] Module handlers/services/repositories không phụ thuộc vào route của feature khác.
- [ ] Tạo một `RouterFunction<ServerResponse>` bean composition rõ ràng khi child paths tương đối.
- [ ] Mọi static/constrained routes đứng trước variable/wildcard/catch-all.
- [ ] Nest path prefix đúng, không nhân đôi `/api/books`.
- [ ] Nested Accept/Content-Type predicates chỉ áp cho nhóm mong muốn.
- [ ] Reactive WebFlux `queryParam` đúng package; không import Servlet `param`.
- [ ] Handler return `Mono<ServerResponse>`, không tự subscribe/block.
- [ ] DTO/input/path/headers được validate, JSON codec xử lý body một lần.
- [ ] HTTP status 400/404/201 và Location/error codes có contract rõ.
- [ ] Router filters có scope cụ thể và không thay auth/CSRF/CORS.
- [ ] Error mapping không leak exception internals hay thông tin user.
- [ ] Không dùng unbounded queues/schedulers cho blocking service.
- [ ] WebTestClient kiểm route correctness, **body**, chứ không chỉ status.
- [ ] Có test cho featured vs ID và collection vs detail/fallback.
- [ ] Auth/tenant ownership được thực thi cả trên nested routes.
- [ ] API versioning không phá hợp đồng DTO/business semantics cũ.
- [ ] Docs/OpenAPI bao phủ functional routes và client examples.
- [ ] CI chạy tests khi thêm/bớt modules để phát hiện route conflicts.
- [ ] Production observability dùng trace IDs và bounded metric labels.

### Câu hỏi tự kiểm tra

**1.** `path("/api/books", builder)` làm gì?

**Trả lời:** Tạo nhóm router với common path prefix; các child paths bên trong được match tương ứng dưới `/api/books`, không yêu cầu mỗi child lặp prefix.

**2.** `nest(accept(APPLICATION_JSON), ...)` có bắt buộc POST cùng builder trả JSON không?

**Trả lời:** Chỉ những routes bên trong nest chịu điều kiện Accept đó. POST bên ngoài nhánh nest không bị áp predicate chỉ vì cùng parent path.

**3.** Khi nào nên dùng `RouterFunction.and(...)` so với Builder `add(...)`?

**Trả lời:** Cả hai hợp thành routers theo thứ tự. `and` tiện nối hai RouterFunctions; `add` tiện thêm router đã tạo vào DSL builder. `path(..., supplier)` tốt khi composition root sở hữu URL prefix cho child router.

**4.** Điều gì xảy ra nếu `GET("/{id}")` đứng trước `GET("/featured")`?

**Trả lời:** Request `/featured` có thể match variable `{id}` trước, khiến handler sai được chọn. Test body/error code cần bắt regression đó.

**5.** Vì sao child router không nên tự là @Bean nếu root cũng dùng path prefix?

**Trả lời:** Một RouterFunction bean child có thể được đăng ký độc lập với relative URLs. Đặt một root RouterFunction bean và child modules là components thường giúp không leak routes ngoài prefix.

**6.** WebFlux.fn handler trả kiểu gì?

**Trả lời:** Thường `Mono<ServerResponse>`; Servlet WebMvc.fn trả `ServerResponse` sync. Chọn đúng imports và response builders.

**7.** Router predicate header có phải authorization không?

**Trả lời:** Không. Nó chỉ quyết định route match; auth/tenant access kiểm ở SecurityWebFilterChain/domain layer.

**8.** `queryParam("mode","summary")` khác `ServerRequest.queryParam("mode")` thế nào?

**Trả lời:** Factory `RequestPredicates.queryParam` dùng để **chọn route**; method trên `ServerRequest` dùng **đọc** query param sau khi chọn handler.

**9.** Hợp thành routers có tự tạo concurrency không?

**Trả lời:** Không. Nó tổ chức match/dispatch, không tự tạo worker threads hay làm blocking I/O trở thành non-blocking.

**10.** Vì sao test chỉ assert HTTP 400 cho `/featured` chưa đủ?

**Trả lời:** Handler ID sai cũng có thể trả 400. Cần assert error code/message để biết router đã chọn đúng fallback.

## 20. Tài liệu chính thức

- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): RouterFunction, nested path/Accept, composition, filters, handlers.
- [Spring Framework 6.1 — RouterFunctions.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.Builder.html): `path`, `nest`, `add`, `GET`/`POST`, filter/onError.
- [Spring Framework 6.1 — RouterFunctions Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.html): `route`, `nest`, `toHttpHandler`.
- [Spring Framework 6.1 — RequestPredicates Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicates.html): `GET`, `POST`, `accept`, `contentType`, `queryParam`.
- [Spring Framework 6.1 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html): request path/query/headers/body decoding.
- [Spring Framework 6.1 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): reactive body/status/headers.
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): handler mappings/adapters/results.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): reactive HTTP-level integration testing.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): Boot WebFlux configuration và server.
- [Spring Security — Reactive Security](https://docs.spring.io/spring-security/reference/reactive/index.html): reactive SecurityWebFilterChain.
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): CORS policies cho reactive endpoints.

**Ghi nhớ:** trong WebFlux.fn, `path` nhóm routes theo prefix, `nest` nhóm routes theo RequestPredicate, còn `and`/`andRoute`/`add` giúp hợp thành router modules. **Thứ tự matching và ownership của prefixes là trọng tâm thiết kế.** Một composition root rõ ràng, child routes tương đối, filter scope có chủ đích và WebTestClient assertions đúng handler giúp API nhiều tính năng vừa mở rộng được vừa dễ bảo trì.

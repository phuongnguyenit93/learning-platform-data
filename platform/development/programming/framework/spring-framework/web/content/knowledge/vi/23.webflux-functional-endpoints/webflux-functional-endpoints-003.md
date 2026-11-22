# Định tuyến theo đường dẫn, method, header và kiểu nội dung trong Functional WebFlux

## 1. Mục tiêu bài học

**Spring WebFlux.fn** (functional endpoints) là mô hình khai báo HTTP routing và xử lý request bằng các hàm Java, song song với `@RestController`/`@RequestMapping`. Trong WebFlux.fn, một `RouterFunction<ServerResponse>` tìm `HandlerFunction<ServerResponse>` thích hợp dựa trên **RequestPredicate**: đường dẫn (path), HTTP method, header, `Content-Type`, `Accept`, query param và những điều kiện tùy chỉnh. Route phù hợp đầu tiên thường quyết định handler được chọn.

Bài học này thuộc **Functional WebFlux** của Spring Framework, dùng **Java 17+, Spring Boot 3.x và Spring Framework 6.x**, tập trung vào bốn trục routing: **path, method, header, media type**. Bài có mã ứng dụng WebFlux chạy được, `curl` và `WebTestClient`, cùng các tình huống dễ nhầm khi client gửi sai thông tin.

Sau bài học, bạn cần làm được:

- Hiểu `RouterFunction`, `HandlerFunction`, `ServerRequest`, `ServerResponse`, `RequestPredicate`.
- Viết route theo `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS` hoặc `method(HttpMethod)` khi cần.
- Match path tĩnh, path variable, pattern, nested path bằng `.path(...)`, và đọc `request.pathVariable(...)`.
- Dùng `RequestPredicates.headers(...)` để kiểm một hoặc nhiều HTTP headers; phân biệt dữ liệu header với authentication.
- Phân biệt `contentType(MediaType.APPLICATION_JSON)` (loại **request body**) với `accept(MediaType.APPLICATION_JSON)` (loại **response client muốn nhận**).
- Kết hợp predicates bằng `and`, `or`, `negate`; tổ chức thứ tự route để tránh shadowing.
- Biết khi nào mismatch trở thành 404, 405, 406 hoặc 415, tại sao phải kiểm bằng HTTP integration tests thay vì luôn giả định một status.
- Sử dụng nested builder, grouping, test predicate và kiểm route sau thêm/bớt một endpoint.
- Tránh blocking I/O, double-subscription, content negotiation sai, header spoofing và xử lý body trước khi quyết định route.

**Lưu ý phạm vi:** các imports phải là package `org.springframework.web.reactive.function.server`, **không phải** `org.springframework.web.servlet.function.server` của MVC.fn. Hai nhóm API tên gần giống nhau nhưng không cùng stack. Không thêm `spring-boot-starter-web` nếu muốn project demo dùng WebFlux reactive application type mặc định.

## 2. Sơ đồ WebFlux.fn từ HTTP tới hàm xử lý

```text
HTTP client
   |
   | GET /api/books/special
   | Accept: application/json
   v
Reactor Netty / reactive server adapter
   |
   v
WebFilter chain -> DispatcherHandler
   |
   v
RouterFunctionMapping
   |
   v
RouterFunction.route(ServerRequest)
   |
   +-- Route 1: method/path/headers/media predicates? ── no
   +-- Route 2: method/path/headers/media predicates? ── yes
   |                                                   |
   |                                                   v
   |                                           HandlerFunction
   |                                           handle(ServerRequest)
   |                                                   |
   |                                                   v
   |                                           Mono<ServerResponse>
   |                                                   |
   v                                                   v
HandlerFunctionAdapter                        ServerResponseResultHandler
                                                       |
                                                       v
                                              HTTP status, headers, body
                                                       |
                                                       v
                                                     Client
```

Sơ đồ mô tả sự phối hợp logic: `RouterFunctionMapping` chọn một handler; `HandlerFunctionAdapter` gọi handler; `ServerResponseResultHandler` ghi kết quả. Đây là **một pipeline reactive**, không phải một thread hay transaction riêng cho từng hộp.

Đặc tả đơn giản hóa:

```java
// Chữ ký ý tưởng của các contracts có sẵn trong Spring:
interface RouterFunction<T extends ServerResponse> {
    Mono<HandlerFunction<T>> route(ServerRequest request);
}

interface HandlerFunction<T extends ServerResponse> {
    Mono<T> handle(ServerRequest request);
}
```

Đây là **mô tả API rút gọn**, không phải hai interfaces để tạo file mới. Spring đã định nghĩa chúng và có thêm phương thức hỗ trợ như visitor/nesting/filter.

Quan trọng: `RouterFunction` là **router**, không phải request handler. `HandlerFunction` mới thực thi business processing và trả `Mono<ServerResponse>`. Một request không khớp predicate không tự động được thử lại sau khi handler đã bắt đầu rồi gặp lỗi; routing lựa chọn handler trước khi handler đọc/tiêu thụ body.

## 3. Những khái niệm nền tảng

| API | Vai trò | Ví dụ |
| --- | --- | --- |
| `RouterFunctions.route()` | Tạo fluent builder nhiều routes | `.GET(...).POST(...).build()` |
| `RouterFunction<ServerResponse>` | Duyệt predicates, trả handler phù hợp | Bean do Spring Boot nhận diện |
| `RequestPredicate` | Kiểm một điều kiện trên `ServerRequest` | `accept(JSON)`, `contentType(JSON)` |
| `RequestPredicates` | Factory predicates chuẩn | `GET("/x")`, `headers(...)` |
| `HandlerFunction<ServerResponse>` | Gọi logic của endpoint | `handler::getBook` |
| `ServerRequest` | Immutable request API | `pathVariable`, `headers`, `bodyToMono` |
| `ServerResponse` | Builder HTTP response | `ok()`, `status(201)`, `contentType` |
| `RouterFunctionMapping` | WebFlux handler mapping cho routers | Khám phá các RouterFunction beans |
| `HandlerFunctionAdapter` | Gọi functional handler đã chọn | Đưa result vào pipeline |
| `ServerResponseResultHandler` | Viết ServerResponse thành HTTP | Chọn message writers/codecs |

Khác annotated route: `@GetMapping("/books/{id}")` được phân tích theo metadata của `RequestMappingHandlerMapping`. Còn functional routes **được kiểm theo thứ tự đã compose**; route đứng trước mà match sẽ thắng, ngay cả khi bạn đặt route tổng quát trước route cụ thể hơn.

### Khi nào dùng WebFlux.fn?

Functional routing hợp với nhóm muốn tách **routing table** khỏi **request handlers**, sử dụng composition/Java lambdas và gom shared predicates. Annotated controllers vẫn hợp lý khi dự án có nhiều method argument resolvers, Bean Validation annotations và các convention `@ControllerAdvice`. Cả hai chạy trên Spring WebFlux reactive core; functional không “non-blocking hơn” chỉ bởi không dùng annotations.

## 4. Route theo HTTP method

Cách ngắn gọn với builder:

```java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/api/books", handler::list)
    .POST("/api/books", handler::create)
    .PUT("/api/books/{id}", handler::replace)
    .PATCH("/api/books/{id}", handler::patch)
    .DELETE("/api/books/{id}", handler::delete)
    .build();
```

Đây là **snippet** trong method cấu hình có `handler` và các functions tương ứng; không phải source runnable độc lập. Khi gọi `.GET(pattern, handler)`, builder phối hợp predicate **HTTP method GET** với **path pattern**. Tương tự cho POST, PUT, PATCH và DELETE.

Nếu dùng builder thủ công theo predicate:

```java
RouterFunction<ServerResponse> getRoute =
    RouterFunctions.route(
        RequestPredicates.method(HttpMethod.GET)
            .and(RequestPredicates.path("/api/books")),
        handler::list);
```

Snippet cần imports `RouterFunctions`, `RequestPredicates`, `HttpMethod`. Tương tự có `RequestPredicates.GET(String)`, `POST(String)`, `PUT(String)`, `DELETE(String)`, `HEAD(String)` và `OPTIONS(String)`.

### Method không phải “chi tiết không quan trọng”

- GET: đọc resource, không nên tạo side effects quan trọng.
- POST: tạo resource hoặc thực hiện operation theo contract, cần validate body.
- PUT: thay thế/tạo representation theo semantics, idempotency.
- PATCH: sửa một phần resource, cần định nghĩa patch document media type.
- DELETE: xóa resource hoặc đánh dấu xóa, vẫn cần authorization.
- HEAD: tương tự metadata GET nhưng không trả representation body; route/tooling có support riêng.
- OPTIONS: khám phá methods/options và CORS preflight; không nhầm với ứng dụng nghiệp vụ.
- Khác phương thức HTTP có thể khiến route không match dù path giống hệt.

**Không giả định HTTP method mismatch trong WebFlux.fn luôn trả chính xác 405.** Nếu không có handler nào được chọn, tùy RouterFunctionMapping, error handler và cấu hình, response có thể như một no-match 404. Một số hạ tầng Spring/HTTP server có xử lý bổ sung cho OPTIONS/HEAD và CORS. Nếu yêu cầu hợp đồng 405 + `Allow`, thiết kế fallback/method policy có chủ đích và integration-test trên đúng phiên bản/framework.

## 5. Route theo đường dẫn cố định

Ví dụ:

```java
return RouterFunctions.route()
    .GET("/api/health", req ->
        ServerResponse.ok().bodyValue("ok"))
    .GET("/api/version", req ->
        ServerResponse.ok().bodyValue("v1"))
    .build();
```

Đây là snippet có thể đặt trong `@Bean RouterFunction<ServerResponse> routes()`. Mỗi URL được so với pattern đã khai báo. `/api/health` và `/api/health/` **không nhất thiết** là cùng một đường dẫn; Spring Framework 6.x đã thay đổi một số defaults về optional trailing separators, nên phải test nếu ứng dụng cần redirect/canonical URL.

Path matching dùng `PathPattern` (không chỉ `String.equals`) và xử lý URI path đúng ngữ cảnh. URL percent-encoded slash, semicolon, dot segments và Unicode có thể chịu policy của server/gateway/firewall. Không dùng raw path làm filesystem path/authorization key mà không có canonicalization policy.

## 6. Path variable và route cụ thể trước route tổng quát

```java
return RouterFunctions.route()
    .GET("/api/books/special", handler::special)
    .GET("/api/books/{id}", handler::getById)
    .build();
```

Đặt `special` **trước** `/{id}`. Nếu đặt ngược và cả hai predicates match `/api/books/special`, route tổng quát có thể ăn request và coi `id="special"`; functional routing không tự chọn “method cụ thể nhất” như annotated mappings thường làm.

Trong handler:

```java
public Mono<ServerResponse> getById(ServerRequest req) {
    String id = req.pathVariable("id");
    return ServerResponse.ok().bodyValue(
        new BookView(id, "Sách " + id));
}
```

Đây là snippet, `BookView` cần được định nghĩa. `pathVariable("id")` đọc giá trị binding; không nên decode lại percent escapes hoặc dùng làm đường dẫn tệp. Nếu id phải là UUID, validate bằng converter và trả 400 theo contract; nếu user không có quyền xem ID đó, route match không đồng nghĩa authorization thành công.

### Path patterns phổ biến

```text
/api/books              exact path
/api/books/{id}         một segment biến id
/api/books/*            wildcard một path segment theo PathPattern rules
/api/files/**           nhiều path segments ở cuối pattern
/api/{category}/{id}    nhiều variables
```

Khi cần capture nhiều path segments ở cuối, Spring `PathPattern` còn có cú pháp đặc biệt như `{*path}`. Không sử dụng tùy tiện làm “file path từ URL”: hãy validate, canonicalize và map tới resource thuộc server, xét security/quyền.

**Không mặc định** `/api/files/a%2Fb` luôn đi qua được encoded slash; reverse proxy, Netty/Servlet adapters, firewall/decoder policy có thể can thiệp. Tốt hơn dùng ID path-safe hoặc query/JSON body cho dữ liệu chứa slash tự do.

## 7. Nested paths: gom nhóm thay vì lặp tiền tố

Functional builder có `.path(prefix, builderConsumer)`:

```java
@Bean
RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
    return RouterFunctions.route()
        .path("/api/books", b -> b
            .GET("/special", handler::special)
            .GET("/{id}", handler::getById)
            .POST(handler::create))
        .build();
}
```

Đây là snippet cần `@Configuration` và imports, handler methods tương ứng. Các inner patterns được match tương đối với prefix `/api/books`.

So sánh:

```text
path("/api/books", b -> b.GET("/special", ...))
           tương đương route GET /api/books/special

path("/api/books", b -> b.GET("/{id}", ...))
           tương đương route GET /api/books/{id}

path("/api/books", b -> b.POST(...))
           tương đương route POST /api/books
```

`path(...)` hữu ích cho API versioning như `/api/v1`, nhưng version segment là cấu trúc route, **không phải giá trị arbitrary ID** để nhét slash vào.

### Nest theo predicate không phải path

Ngoài `path`, builder có `nest(RequestPredicate, Consumer<Builder>)`, ví dụ:

```java
RouterFunctions.route()
    .path("/api/books", b -> b
        .nest(RequestPredicates.accept(MediaType.APPLICATION_JSON),
              json -> json
                  .GET("/{id}", handler::getById)
                  .GET("/special", handler::special)))
    .build();
```

Đây là snippet. **Thứ tự vẫn quan trọng trong nhánh nested!** Với snippet này `/{id}` đứng trước `/special` nên có thể shadow route cụ thể; phải đảo thứ tự trước khi dùng thật.

Thay vì lặp `accept(JSON)` nhiều lần, nesting biểu đạt một điều kiện chung. Tuy vậy nếu mọi route POST có content-type khác nhau, đừng nest `contentType(JSON)` ngoài cả nhóm khiến form/text branch không bao giờ match.

## 8. Header predicates: lọc theo metadata request

Spring WebFlux.fn có `RequestPredicates.headers(Predicate<ServerRequest.Headers>)`. Ví dụ kiểm header `X-View` có giá trị `trace`:

```java
RequestPredicate debugOnly =
    RequestPredicates.headers(headers ->
        "trace".equals(headers.firstHeader("X-View")));
```

Nếu request gửi:

```http
GET /api/status HTTP/1.1
X-View: trace
```

thì predicate match. Nếu không có header, `firstHeader(...)` trả null, biểu thức `"trace".equals(null)` là false.

**Headers case-insensitive theo HTTP specification** về tên; giá trị cần so sánh theo semantics từng header. Với custom `X-View` do ứng dụng tự định nghĩa, so exact value có thể phù hợp; không tùy tiện normalize Authorization hay signature values.

Có thể kết hợp:

```java
RequestPredicate jsonAndTrace =
    RequestPredicates.headers(h ->
        "trace".equals(h.firstHeader("X-View")))
    .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));
```

Trong builder:

```java
.GET("/api/status", jsonAndTrace, handler::status)
```

Snippet yêu cầu biến `handler`. `RequestPredicates.headers(...)` kiểm **metadata**, không đọc JSON body và không xác thực ai gửi header đó.

### Header là input, không phải authentication

`X-User: admin`/`X-Role: ADMIN` do client gửi không phải chứng cứ danh tính. Nếu gateway đáng tin chèn header identity, phải cấu hình trust boundary, strip headers client tự khai, bảo vệ liên kết nội bộ và kiểm authorization ở backend. Dùng Spring Security reactive `SecurityWebFilterChain` cho authentication/authorization thay vì tự viết một `headers(...)` predicate giả làm access control.

### Header nhiều giá trị

`ServerRequest.Headers` có API cho giá trị đầu hoặc list tùy header. Nếu client gửi hai header cùng tên, proxy có thể gộp/giữ nhiều values; với security-sensitive matching cần định nghĩa policy chống request smuggling/header ambiguity. `firstHeader` phù hợp demo metadata đơn giản, không phải thuật toán canonicalization tổng quát.

## 9. Content-Type: mô tả request body

`Content-Type` trong request mô tả **loại representation mà client gửi**. Với POST:

```http
POST /api/books HTTP/1.1
Content-Type: application/json

{"title":"WebFlux"}
```

Để route chỉ nhận JSON:

```java
.POST("/api/books",
      RequestPredicates.contentType(MediaType.APPLICATION_JSON),
      handler::createJson)
```

Nếu client gửi `Content-Type: text/plain`, predicate này không match. Đừng cố `bodyToMono(BookInput.class)` cho plain text bằng cách “đổi route” khi codec không hỗ trợ.

### Charset và content-type compatibility

Media types có type/subtype và có thể parameters như charset/boundary. `contentType(APPLICATION_JSON)` là predicate theo compatibility semantics, không phải đơn giản `headerString.equals("application/json")`. Với JSON có charset parameter như `application/json;charset=UTF-8`, predicate vẫn có thể phù hợp.

**Media type matching không tự bảo đảm body hợp lệ**: JSON syntax hỏng nhưng Content-Type là `application/json` vẫn match route; sau đó Jackson decoder có thể phát error, thường HTTP 400. Ngược lại một body JSON hợp lệ gửi dưới `text/plain` không nên coi là JSON chỉ vì bytes trông giống JSON.

### Form và multipart

`application/x-www-form-urlencoded` và `multipart/form-data` là hai media types khác. WebFlux.fn `ServerRequest.bodyToMono(...)`/`formData()`/`multipartData()` có APIs tùy content type; không đọc multipart file content như String vô hạn trong event loop. Multipart cần limits về size/count và cleanup `DataBuffer`/`Part` đúng.

## 10. Accept: client muốn nhận gì?

`Accept` là **khả năng nhận response representation**, không phải mô tả request body.

```http
GET /api/books/42 HTTP/1.1
Accept: application/json
```

Predicate:

```java
.GET("/api/books/{id}",
     RequestPredicates.accept(MediaType.APPLICATION_JSON),
     handler::getById)
```

Khi match, handler có thể trả JSON với:

```java
return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new BookView("42", "WebFlux"));
```

**Phân biệt hai giai đoạn:** `accept(JSON)` quyết định **route có phù hợp** theo request headers; `ServerResponse.contentType(JSON)` chọn **Content-Type của response** và codecs thực sự ghi body. Chỉ viết `accept(JSON)` không tự buộc handler phải trả JSON nếu handler cố ý viết text; ngược lại set response Content-Type không đảm bảo route đã match theo Accept.

### Accept wildcard, specificity và q-value

Ví dụ:

```http
Accept: */*
Accept: application/json
Accept: application/json, text/plain;q=0.5
Accept: text/*;q=0.8, application/json;q=0.4
```

Media type matching theo compatibility; wildcard có thể chấp nhận nhiều representations. Không viết code `request.headers().firstHeader("Accept").equals("application/json")` để triển khai content negotiation. Spring `RequestPredicates.accept(...)` giúp dùng semantics của HTTP media types; nếu cần chọn giữa nhiều representations dựa trên preference, hãy định nghĩa routes có thứ tự và test thực tế, hoặc dùng content negotiation strategy phù hợp.

**Lưu ý quan trọng:** Hai route khác nhau cùng path/method nhưng `accept(JSON)` và `accept(TEXT_PLAIN)` có thể **cùng match** một client gửi `Accept: */*`. Khi đó thứ tự functional routes quyết định handler nào được chọn. Vì vậy đừng coi `Accept` là độc quyền trừ khi client contract và route order được kiểm soát.

## 11. Tạo route theo cả Content-Type và Accept

Một endpoint nhận JSON và trả JSON:

```java
RequestPredicate jsonRequestAndResponse =
    RequestPredicates.contentType(MediaType.APPLICATION_JSON)
        .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));

RouterFunction<ServerResponse> router = RouterFunctions.route()
    .POST("/api/books", jsonRequestAndResponse, handler::createJson)
    .build();
```

Đây là snippet trong class có `handler`. Request cần gửi cả đúng `Content-Type` lẫn `Accept` tương thích:

```http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Routing"}
```

Nếu client gửi `Content-Type: text/plain` và `Accept: application/json`, JSON route không match vì request body type sai. Nếu client gửi `Content-Type: application/json` và `Accept: text/plain`, JSON route không match vì representation output không được chấp nhận.

**Hợp đồng route là logic AND**, nhưng HTTP status mặc định khi không match không thể suy chỉ từ boolean. Còn tùy các routes khác, fallback, handlers và WebFlux version, một mismatch có thể thể hiện như no-handler 404 hoặc lỗi 406/415 do infrastructure đánh giá media mismatch. Nếu API contract yêu cầu cụ thể 406/415, integration tests phải chứng minh và có error policy tường minh khi cần.

## 12. Kết hợp predicates bằng and, or và negate

`RequestPredicate` cung cấp composition:

```java
RequestPredicate wantsJson =
    RequestPredicates.accept(MediaType.APPLICATION_JSON);

RequestPredicate internalView =
    RequestPredicates.headers(h ->
        "internal".equals(h.firstHeader("X-View")));

RequestPredicate strict =
    wantsJson.and(internalView);

RequestPredicate either =
    wantsJson.or(RequestPredicates.accept(MediaType.TEXT_PLAIN));

RequestPredicate notInternal = internalView.negate();
```

Các biến trên là code snippet trong Java method có static imports hoặc imports.

- `A.and(B)`: request phải thỏa **cả hai**.
- `A.or(B)`: ít nhất một phù hợp.
- `A.negate()`: đảo điều kiện.
- Composition có thể short-circuit; đừng đặt side effects quan trọng trong predicate rồi giả định nó luôn chạy.
- Predicates nên là các phép kiểm nhanh, không chặn I/O và không thay đổi resource state.
- Những điều kiện tổ hợp khó đọc nên được đặt tên hàm/biến như `jsonOnly`, `traceView`, `businessVersion` và có test riêng.

### Khi cần custom RequestPredicate

```java
RequestPredicate validApiKeyFormat = request ->
    request.headers().firstHeader("X-Api-Key") != null;
```

Đây chỉ là **kiểm sự hiện diện** của header, **không kiểm secret thực**, không đủ bảo vệ API. Hạn chế custom predicates tới các request-routing criteria ổn định; xác thực dùng Spring Security, validation business sau khi route match. Một predicate không nên gọi DB blocking hoặc tự subscribe reactive pipeline chỉ để quyết định route.

## 13. Functional routing có ưu tiên theo thứ tự khai báo

Theo Spring Framework reference, các routes được đánh giá **theo thứ tự**. Khi route đầu tiên match, route sau không được ưu tiên chỉ vì pattern cụ thể hơn.

Sai:

```java
RouterFunctions.route()
    .GET("/api/books/{id}", handler::getById)
    .GET("/api/books/special", handler::special)
    .build();
```

Request `GET /api/books/special` có thể vào `getById` với `id="special"`.

Đúng:

```java
RouterFunctions.route()
    .GET("/api/books/special", handler::special)
    .GET("/api/books/{id}", handler::getById)
    .build();
```

**Nested cũng không tự sửa route ordering.** Trong cùng một `.path(prefix, b -> ...)`, vẫn khai báo special before variable. Nếu tách nhiều `RouterFunction` beans, `RouterFunctionMapping` có thể sắp xếp/ghép beans theo `Ordered`; đừng kỳ vọng lexical bean name hoặc source file order luôn thắng. Nếu route order có ý nghĩa nghiệp vụ, gộp vào một router builder rõ ràng hoặc đánh `@Order` một cách có kiểm thử.

### Điều kiện header/media có thể shadow nhau

Nếu route rộng `GET("/api/books", handler::all)` đứng trước route `GET("/api/books", headers(...), handler::special)`, mọi request match route rộng sẽ đi vào `all`, kể cả có header đặc biệt. Cần đặt route cụ thể có header predicate **trước**, hoặc thiết kế khác path để tránh ambiguity.

Nếu bạn đặt GET JSON trước GET text trên cùng path và client dùng Accept wildcard, JSON có thể thắng. Điều này không phải bug codec; đó là route order logic.

## 14. Route theo query parameter (phụ trợ)

Mặc dù trọng tâm là path/method/header/media, query params thường cần trong route conditions:

```java
RouterFunctions.route()
    .GET("/api/books",
        RequestPredicates.queryParam("view", "compact"),
        handler::compact)
    .GET("/api/books", handler::list)
    .build();
```

Request `?view=compact` chọn route đầu tiên; thiếu hoặc khác thì route thứ hai. Đặt route conditional trước route fallback. `queryParam` kiểm query **đã parse**, không phải kiểm raw URI bằng substring. Nếu dữ liệu chứa `&`/`=` thì phải encode đúng component; không gọi `URLDecoder` hai lần.

Với nhiều values cùng tên, đừng coi một queryParam predicate là full validation của repeated parameter policy. Handler có thể dùng `request.queryParams()`/`queryParam(...)` và định nghĩa có nhận duplicates hay không.

**Không đưa identity/authorization vào query parameter một cách thiếu bảo mật**: `?role=admin` không phải permission và query thường xuất hiện trong logs/history.

## 15. Ghi response với ServerResponse

Functional handler trả `Mono<ServerResponse>`, thường tạo bằng builder:

```java
public Mono<ServerResponse> okBook(ServerRequest request) {
    BookView body = new BookView(
        request.pathVariable("id"), "Đọc sách");

    return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(body);
}
```

Đây là snippet, cần record `BookView` tương ứng.

Các patterns:

| Builder | Ý nghĩa |
| --- | --- |
| `ServerResponse.ok()` | HTTP 200 |
| `ServerResponse.status(HttpStatus.CREATED)` | HTTP 201 |
| `ServerResponse.accepted()` | HTTP 202 |
| `ServerResponse.noContent()` | HTTP 204 không body |
| `ServerResponse.badRequest()` | HTTP 400 |
| `ServerResponse.notFound()` | HTTP 404 |
| `ServerResponse.status(HttpStatus.UNSUPPORTED_MEDIA_TYPE)` | HTTP 415 nếu app chủ động trả |
| `.header("X-Request-Id", id)` | Response header |
| `.contentType(MediaType.APPLICATION_JSON)` | Representation của response |
| `.bodyValue(dto)` | Encode regular body value qua codecs |
| `.body(flux, Dto.class)` | Viết reactive body stream |

Tạo `Mono<ServerResponse>` không có nghĩa bytes đã gửi ngay; HTTP infrastructure sẽ subscribe, invoke `ServerResponseResultHandler` và codecs, rồi ghi dữ liệu đúng response lifecycle.

### Đọc request body sau khi route phù hợp

```java
public Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateBook.class)
        .flatMap(input ->
            ServerResponse.status(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new BookView("book_1", input.title())));
}
```

Snippet chưa xử lý empty/invalid body. Trong app thực thêm `switchIfEmpty(ServerResponse.badRequest().build())` và validation. Router predicate `contentType` **không thay thế** JSON decoding hoặc Bean Validation.

Không gọi `request.bodyToMono(...).block()` trong handler; Netty event loop không dành cho blocking work.

## 16. Ứng dụng hoàn chỉnh Spring Boot 3 Java 17+

Project Maven tạo bằng Spring Initializr, dependencies:

- `spring-boot-starter-webflux` (runtime).
- `spring-boot-starter-test` (test scope).
- `io.projectreactor:reactor-test` nếu không được kéo vào qua test starter phù hợp.

Không cần database, Spring Security, Servlet MVC hay template engine. Các files:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  BookHandler.java
  BookRoutes.java
src/test/java/com/example/demo/
  BookRoutesTest.java
```

**Các endpoints demo:**

| Method | URL | Predicate thêm | Result |
| --- | --- | --- | --- |
| GET | `/api/books/special` | `Accept` JSON | JSON book đặc biệt |
| GET | `/api/books/{id}` | `Accept` JSON | JSON book với ID |
| POST | `/api/books` | `Content-Type` JSON **and** `Accept` JSON | 201 JSON |
| POST | `/api/books` | `Content-Type` text/plain **and** `Accept` text/plain | 200 text |
| GET | `/api/status` | `X-View: trace` | JSON trạng thái |
| GET | `/api/stream` | `Accept` SSE | Ba SSE events |
| GET | `/api/docs/hello` | Nested path | JSON lời chào |

Routes có cùng path/method cho POST nhưng **Content-Type phân biệt rõ**; không đoán representation chỉ theo body. Test sẽ gửi `Accept` tường minh để tránh wildcard ambiguity.

### 16.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 16.2. BookHandler.java

```java
package com.example.demo;

import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class BookHandler {

    public Mono<ServerResponse> special(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new BookView("special", "Sách đặc biệt"));
    }

    public Mono<ServerResponse> getById(ServerRequest request) {
        String id = request.pathVariable("id");

        if (!id.matches("[A-Za-z0-9_-]{1,64}")) {
            return ServerResponse.badRequest().build();
        }

        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new BookView(id, "Book " + id));
    }

    public Mono<ServerResponse> createJson(ServerRequest request) {
        return request.bodyToMono(CreateBook.class)
            .flatMap(input -> {
                if (input.title() == null ||
                    input.title().isBlank() ||
                    input.title().length() > 120) {
                    return ServerResponse.badRequest().build();
                }

                return ServerResponse.status(HttpStatus.CREATED)
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(new BookView("book_1",
                                             input.title()));
            })
            .switchIfEmpty(ServerResponse.badRequest().build());
    }

    public Mono<ServerResponse> createText(ServerRequest request) {
        return request.bodyToMono(String.class)
            .flatMap(raw -> {
                if (raw.isBlank() || raw.length() > 120) {
                    return ServerResponse.badRequest().build();
                }
                return ServerResponse.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .bodyValue("text:" + raw);
            })
            .switchIfEmpty(ServerResponse.badRequest().build());
    }

    public Mono<ServerResponse> status(ServerRequest request) {
        // X-View là request metadata, không là authentication.
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new StatusView("trace"));
    }

    public Mono<ServerResponse> events(ServerRequest request) {
        Flux<NumberEvent> data = Flux.range(1, 3)
            .delayElements(Duration.ofMillis(60))
            .map(NumberEvent::new);

        return ServerResponse.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(data, NumberEvent.class);
    }

    public Mono<ServerResponse> docsHello(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new StatusView("docs-hello"));
    }

    public record BookView(String id, String title) {}
    public record CreateBook(String title) {}
    public record StatusView(String mode) {}
    public record NumberEvent(int value) {}
}
```

Giải thích:

- `BookHandler` là Spring bean có methods nhận `ServerRequest` và trả `Mono<ServerResponse>`.
- `getById` validate ID path-safe nhưng **không** thay authorize domain resource ở production.
- `createJson` nhận JSON body và trả 201; mỗi request demo tạo cùng ID `book_1` để đơn giản hóa, **không** có durable persistence. Production cần DB uniqueness, idempotency và permission.
- `createText` nhận `text/plain`, không deserialize thành JSON.
- `status` không đọc/suy role từ `X-View`; header chỉ định dạng route demo.
- `events` trả finite `Flux` với Content-Type SSE; delay chỉ để quan sát, không phải cam kết latency thực.
- `switchIfEmpty(ServerResponse.badRequest().build())` xử lý body rỗng; không tự tạo second subscription lên body stream.
- Với malformed JSON, decoder có thể phát error trước khi `flatMap` chạy; HTTP status/body lỗi phụ thuộc WebFlux error handling. Muốn thống nhất error contract, bổ sung `WebExceptionHandler`/functional routing error handler theo chính sách.

### 16.3. BookRoutes.java

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicate;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class BookRoutes {

    @Bean
    public RouterFunction<ServerResponse> functionalBookRoutes(
            BookHandler handler) {

        RequestPredicate jsonInputAndOutput =
            RequestPredicates.contentType(MediaType.APPLICATION_JSON)
                .and(RequestPredicates.accept(
                    MediaType.APPLICATION_JSON));

        RequestPredicate textInputAndOutput =
            RequestPredicates.contentType(MediaType.TEXT_PLAIN)
                .and(RequestPredicates.accept(MediaType.TEXT_PLAIN));

        RequestPredicate traceHeader =
            RequestPredicates.headers(h ->
                "trace".equals(h.firstHeader("X-View")));

        return RouterFunctions.route()

            // Đặt /special trước /{id} để route cụ thể thắng.
            .path("/api/books", b -> b
                .GET("/special",
                     RequestPredicates.accept(
                         MediaType.APPLICATION_JSON),
                     handler::special)
                .GET("/{id}",
                     RequestPredicates.accept(
                         MediaType.APPLICATION_JSON),
                     handler::getById)
                .POST(jsonInputAndOutput, handler::createJson)
                .POST(textInputAndOutput, handler::createText))

            .GET("/api/status", traceHeader, handler::status)

            .GET("/api/stream",
                 RequestPredicates.accept(
                     MediaType.TEXT_EVENT_STREAM),
                 handler::events)

            .path("/api/docs", b -> b
                .GET("/hello", handler::docsHello))

            .build();
    }
}
```

Vì sao đây là ví dụ tốt cho đề bài:

1. **Path**: nested `/api/books`, `/api/docs`; route `/special` trước `/{id}`.
2. **Method**: GET và POST không bị nhập làm một.
3. **Header**: `/api/status` chỉ match khi `X-View` bằng `trace`.
4. **Content-Type**: chọn POST JSON hoặc POST text.
5. **Accept**: yêu cầu client chấp nhận representation tương ứng, thêm SSE riêng.
6. **Composition**: `and` buộc cả input và output media-type conditions.
7. **Không shadow**: các routes chung path/method phân biệt bởi explicit predicates.
8. **Không tùy tiện dùng @EnableWebFlux**: để Spring Boot WebFlux auto-configuration tạo hạ tầng đúng.

### 16.4. Chạy demo

Trong thư mục project Maven có wrapper:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Cổng mặc định thường `8080` nếu không chỉnh `server.port`. Các source Spring cần dependency classpath; không chạy `javac BookRoutes.java` độc lập khi thiếu Spring/Reactor libraries.

## 17. curl: GET path và Accept

### Route đặc biệt

```bash
curl -i 'http://localhost:8080/api/books/special' \
  -H 'Accept: application/json'
```

Kỳ vọng HTTP 200 và JSON:

```json
{"id":"special","title":"Sách đặc biệt"}
```

Mục đích test: `/special` đã được match **trước** `/{id}`. Nếu đảo route order, cùng request có thể vào generic handler và trả `{"id":"special","title":"Book special"}`. Đây là dấu hiệu rõ của shadowing.

### Route variable

```bash
curl -i 'http://localhost:8080/api/books/book_42' \
  -H 'Accept: application/json'
```

Kỳ vọng:

```json
{"id":"book_42","title":"Book book_42"}
```

Dữ liệu path variable do application validate theo format `[A-Za-z0-9_-]{1,64}`. `/api/books/../../secret` không phải cách hợp lệ đọc resource và có thể bị gateway normalizer/canonicalizer xử lý sớm; vẫn cần authorization/ID mapping phía server.

### Đường dẫn nested

```bash
curl -i 'http://localhost:8080/api/docs/hello'
```

Kỳ vọng HTTP 200:

```json
{"mode":"docs-hello"}
```

Endpoint không yêu cầu `Accept` predicate nhưng handler vẫn đặt `Content-Type: application/json`. Nếu client không chấp nhận JSON và gửi Accept khác, hạ tầng codec/content negotiation hoặc error handler có thể phản ứng khác; route match không thay việc viết representation phù hợp.

## 18. curl: kiểm header predicate

```bash
curl -i 'http://localhost:8080/api/status' \
  -H 'X-View: trace'
```

Kỳ vọng HTTP 200:

```json
{"mode":"trace"}
```

Nếu bỏ `X-View` hoặc gửi `X-View: debug`, predicate không match. Trong project demo không có route fallback cho `/api/status` nên thường trả HTTP 404 (cũng tùy error layer); kiểm trực tiếp bằng integration tests thay vì coi header không tồn tại tự tạo 403.

**Tại sao không 403?** Header predicate chỉ định tuyến, không là authorization mechanism. Để bảo vệ endpoint hãy khai báo Spring Security policies và kiểm user/role/tenant. Trả 404 cho route không match và 403 cho user không đủ quyền là hai vấn đề khác nhau.

## 19. curl: POST Content-Type và Accept

### 19.1. JSON vào, JSON ra

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"title":"Học Spring WebFlux"}'
```

Kỳ vọng status **201 Created** và JSON:

```json
{"id":"book_1","title":"Học Spring WebFlux"}
```

Tại sao phải có cả hai headers? `Content-Type` mô tả JSON body, `Accept` báo client có thể nhận JSON. Client gửi `Accept: */*` vẫn có thể match JSON route theo compatibility; đây không phải công tắc yêu cầu header phải xuất hiện literal `application/json`.

### 19.2. Plain text vào, plain text ra

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: text/plain' \
  -H 'Accept: text/plain' \
  --data-binary 'hello'
```

Kỳ vọng status 200, `Content-Type: text/plain`, body:

```text
text:hello
```

Cùng URL + POST nhưng Content-Type khác, vì vậy handler khác.

### 19.3. Trộn sai Content-Type/Accept

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/plain' \
  -d '{"title":"not-matched"}'
```

Không route nào trong demo thỏa **đồng thời** cả hai điều kiện. **Không hardcode một mã trạng thái duy nhất cho mọi phiên bản WebFlux**, bởi xử lý no-match/media mismatch có thể thông qua RouterFunctionMapping/WebExceptionHandler; hãy xem HTTP thật và quyết định có cần error contract riêng hay không.

Đặc biệt, status 415 nên biểu thị request media type không được hỗ trợ, 406 biểu thị representation không được chấp nhận; 404 biểu thị không có resource/route phù hợp. Các nghĩa HTTP khác nhau, nhưng functional predicate mismatch **không phải** annotation `consumes/produces` tự sinh mọi status như nhau.

### 19.4. JSON malformed

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"title":'
```

Predicate Content-Type và Accept vẫn match; **body parser** khi đọc `CreateBook` thất bại, thường trả 400 qua WebFlux error infrastructure. Không viết predicate dựa vào body JSON content khi body đã được consume một lần.

### 19.5. Request thiếu body

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary ''
```

Route vẫn match theo Content-Type; `bodyToMono` complete empty và handler `switchIfEmpty` trả 400. Đừng nhầm “route matched” với “body passes validation”.

## 20. curl: Server-Sent Events và media negotiation

```bash
curl -N -i 'http://localhost:8080/api/stream' \
  -H 'Accept: text/event-stream'
```

Kỳ vọng status 200, `Content-Type: text/event-stream` và các sự kiện:

```text
data:{"value":1}

data:{"value":2}

data:{"value":3}

```

Reactor `Flux.range(1,3).delayElements(...)` phát ba phần tử theo thứ tự. `curl -N` tắt buffering ở curl, nhưng **mỗi SSE event không đồng nghĩa một TCP packet**, timing không chắc chắn chính xác mỗi 60ms. Nếu client disconnect sớm, downstream có thể cancel subscription.

SSE đòi giới hạn số connections, kích thước buffer, idle timeouts, xác thực và chính sách reconnect/replay. Content negotiation giúp chọn codec, không tự giới hạn memory.

## 21. WebTestClient: kiểm route đúng và sự khác biệt predicates

Tệp `src/test/java/com/example/demo/BookRoutesTest.java`:

```java
package com.example.demo;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BookRoutesTest {

    @Autowired
    WebTestClient client;

    @Test
    void specificPathWinsBeforeIdPath() {
        client.get().uri("/api/books/special")
            .accept(MediaType.APPLICATION_JSON)
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("special")
            .jsonPath("$.title").isEqualTo("Sách đặc biệt");
    }

    @Test
    void pathVariableIsBoundIntoHandler() {
        client.get().uri("/api/books/book_42")
            .accept(MediaType.APPLICATION_JSON)
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("book_42")
            .jsonPath("$.title").isEqualTo("Book book_42");
    }

    @Test
    void headerPredicateSelectsRoute() {
        client.get().uri("/api/status")
            .header("X-View", "trace")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.mode").isEqualTo("trace");
    }

    @Test
    void missingHeaderDoesNotMatchThisRoute() {
        client.get().uri("/api/status")
            .exchange().expectStatus().isNotFound();
    }

    @Test
    void jsonInputAndJsonAcceptUseJsonHandler() {
        client.post().uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "WebFlux"))
            .exchange().expectStatus().isCreated()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("book_1")
            .jsonPath("$.title").isEqualTo("WebFlux");
    }

    @Test
    void textInputAndTextAcceptUseTextHandler() {
        client.post().uri("/api/books")
            .contentType(MediaType.TEXT_PLAIN)
            .accept(MediaType.TEXT_PLAIN)
            .bodyValue("hello")
            .exchange().expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_PLAIN)
            .expectBody(String.class).isEqualTo("text:hello");
    }

    @Test
    void emptyJsonBodyFailsValidation() {
        client.post().uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue("")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void nestedPathIsMatched() {
        client.get().uri("/api/docs/hello")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.mode").isEqualTo("docs-hello");
    }

    @Test
    void sseStreamEmitsThreeItems() {
        Flux<BookHandler.NumberEvent> events = client.get()
            .uri("/api/stream")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange().expectStatus().isOk()
            .returnResult(BookHandler.NumberEvent.class)
            .getResponseBody();

        StepVerifier.create(events)
            .expectNext(new BookHandler.NumberEvent(1))
            .expectNext(new BookHandler.NumberEvent(2))
            .expectNext(new BookHandler.NumberEvent(3))
            .verifyComplete();
    }
}
```

**Đây là bộ test mẫu chưa được thực thi trong repository của người dùng.** Spring Boot 3/WebTestClient/Netty codecs cần đúng dependencies đã nêu.

**Caveat đối với test empty JSON:** `bodyValue("")` với `contentType(APPLICATION_JSON)` có thể được JSON encoder diễn giải thành một JSON string literal `""` thay vì request body 0 byte; khi đó decoder cho `CreateBook` vẫn tạo lỗi 400, nhưng không chứng minh nhánh `switchIfEmpty`. Để kiểm chính xác zero-length request body, dùng `BodyInserters.empty()`/request body rỗng tương ứng và assert. Tùy codec/version, nên tách test malformed JSON và empty body riêng.

**Caveat đối với SSE codec:** một số cấu hình WebTestClient có thể decode SSE thành `ServerSentEvent<NumberEvent>` hoặc cần `ParameterizedTypeReference` thay vì DTO class trực tiếp. Nếu gặp codec mismatch, sử dụng kiểu `ServerSentEvent<BookHandler.NumberEvent>` đúng và assert `event.data()`; không coi một network chunk là một event. Test `returnResult`/`StepVerifier` về mặt khái niệm đúng.

**Caveat đối với no-match:** Test thiếu header kỳ vọng 404 ở cấu hình demo chuẩn; nếu application thêm exception handler/fallback router, hợp đồng phải được cập nhật. Đừng cố bắt 404 cho một ứng dụng đã tùy biến để trả status khác.

Chạy tests:

```bash
./mvnw test
```

Windows PowerShell:

```powershell
.\mvnw.cmd test
```

Nếu bật Spring Security reactive, các endpoint POST có thể đòi CSRF token và các request không xác thực có thể nhận 401/403 trước router; test cần cấu hình authentication/CSRF đúng policy. Demo không có Spring Security.

## 22. Kiểm thử thuần RouterFunction không cần HTTP server

Khi muốn test route selection nhanh, Spring có thể tạo `ServerRequest` giả qua `MockServerRequest` (API trong spring-test) hoặc dùng `WebTestClient.bindToRouterFunction(routes)` để không cần mở cổng.

Ý tưởng:

```java
WebTestClient client = WebTestClient
    .bindToRouterFunction(bookRoutes)
    .build();
```

Snippet dùng biến `bookRoutes` và imports `org.springframework.test.web.reactive.server.WebTestClient`. Với `bindToRouterFunction`, có thể kiểm các predicates/handlers mà không chạy Netty; nhưng **không nhất thiết** gồm toàn bộ security/filter/exception infrastructure của Boot app. Vì vậy dùng cả unit test router và HTTP integration test khi cần xác minh status, media negotiation, CORS hoặc proxy behavior.

### Test contract bằng ma trận thay vì một happy path

| Method | Path | X-View | Content-Type | Accept | Route mong muốn |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/books/special` | — | — | JSON | `special` |
| GET | `/api/books/book_42` | — | — | JSON | `getById` |
| POST | `/api/books` | — | JSON | JSON | `createJson` |
| POST | `/api/books` | — | text/plain | text/plain | `createText` |
| GET | `/api/status` | trace | — | */* | `status` |
| GET | `/api/status` | absent | — | */* | Không match route status |
| GET | `/api/stream` | — | — | text/event-stream | `events` |
| GET | `/api/docs/hello` | — | — | */* | `docsHello` |

Các dấu `—` nghĩa header không cần cho predicate đang xét. Riêng HTTP request GET không có body, `Content-Type` thường không quan trọng; đừng bắt GET client gửi Content-Type chỉ để match một response type. `Accept` thường có wildcard default nếu client không đặt.

Đặc biệt thử thêm các trường hợp `Accept: */*`, header lowercase/uppercase, query duplicates, encoded path, trailing slash, OPTIONS/CORS preflight và các method sai để phát hiện ambiguity.

## 23. Java 17 thuần: minh họa route order deterministic

Phần này không dùng Spring. Nó chỉ dùng Java 17 để chứng minh một router functional đơn giản đi qua danh sách điều kiện **theo thứ tự** và chọn điều kiện đầu tiên đúng.

Tệp `RouteOrderDemo.java`:

```java
import java.util.List;
import java.util.function.Predicate;

public class RouteOrderDemo {

    record Request(String method, String path, String accept) {}
    record Route(String name, Predicate<Request> matches) {}

    public static void main(String[] args) {
        List<Route> wrongOrder = List.of(
            new Route("byId",
                r -> r.method().equals("GET") &&
                     r.path().startsWith("/books/")),
            new Route("special",
                r -> r.method().equals("GET") &&
                     r.path().equals("/books/special"))
        );

        List<Route> rightOrder = List.of(
            wrongOrder.get(1),
            wrongOrder.get(0)
        );

        Request req = new Request(
            "GET", "/books/special", "application/json");

        System.out.println("wrong=" + choose(wrongOrder, req));
        System.out.println("right=" + choose(rightOrder, req));
    }

    private static String choose(
            List<Route> routes, Request request) {
        return routes.stream()
            .filter(route -> route.matches().test(request))
            .map(Route::name)
            .findFirst()
            .orElse("not-found");
    }
}
```

Biên dịch/chạy:

```bash
javac RouteOrderDemo.java
java RouteOrderDemo
```

Stdout chính xác:

```text
wrong=byId
right=special
```

Chương trình này minh họa ý tưởng **first matching predicate** chứ không tự thực thi Spring `PathPattern`, MIME compatibility, headers parsing hay Reactor. Để xác minh WebFlux.fn thực sự, dùng các tests của project Boot ở trên.

## 24. Bảo mật khi route theo header và đường dẫn

Routing theo header/path/content-type **không thay authentication, authorization hoặc input validation**:

- `X-User`, `X-Tenant`, `X-Role` do client tự khai không phải identity đáng tin.
- `RequestPredicates.headers(h -> "admin".equals(...))` là branch selection, không phải security guard.
- Dùng Spring Security `SecurityWebFilterChain`, bảo vệ routes và kiểm resource-level permissions sau khi bind ID.
- Cần xét các route functional và annotated cùng WebFlux application; một rule chỉ match annotation metadata có thể bỏ sót functional route nếu config không đúng.
- CORS preflight OPTIONS có thể được xử lý bởi `CorsWebFilter`/security chain trước route; đừng tạo route OPTIONS trả “cho phép hết” để bỏ qua policy.
- Content-Type không chứng minh body an toàn: validate kích thước, JSON syntax, schema và business rules.
- Accept không ngăn HTML/XSS nếu bạn ghi dữ liệu không được escape vào `text/html`; dùng output encoding theo context.
- Raw path/encoded slash và trailing slash cần canonicalization nhất quán qua proxy/server/security.
- Kiểm soát method override từ gateway/proxy nếu có; tránh hạ tầng hiểu POST thành PUT/PATCH khác nhau.
- Không log toàn bộ `Authorization`/`Cookie`/query string để debug route mismatch.
- Với multipart uploads và form parsing, có giới hạn size/count và cleanup `DataBuffer`.
- Path variable không được trực tiếp nối vào filesystem path để mở file.

**Chính sách nguồn tin cậy** cần đặt ở chỗ authentication/security; predicates chỉ nên kiểm metadata request phục vụ dispatch.

## 25. Khi nào status 404, 405, 406, 415?

HTTP semantics:

| Status | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `404 Not Found` | Không có representation/resource phù hợp được tiết lộ | Không route match hoặc server chủ ý ẩn resource |
| `405 Method Not Allowed` | URL/resource có tồn tại nhưng method không được hỗ trợ | Cần `Allow` header thích hợp |
| `406 Not Acceptable` | Không có response representation client chấp nhận | `Accept` không tương thích |
| `415 Unsupported Media Type` | Body Content-Type không được hỗ trợ | Client gửi content type sai |
| `400 Bad Request` | Input sai format/schema/validation | JSON malformed, path ID invalid, required field missing |
| `401 Unauthorized` | Chưa xác thực theo policy | Security entrypoint |
| `403 Forbidden` | Đã xác thực nhưng không đủ quyền | Authorization failure |

**Đừng suy** rằng `RequestPredicates.accept(...)` false **luôn** sinh 406, hoặc `contentType(...)` false **luôn** sinh 415. Trong WebFlux.fn, predicate false thường chỉ làm router tìm route khác; cách error được dựng khi hết routes phụ thuộc mapping/error infrastructure và các route khác. Với annotated controllers, Spring có nhiều loại mismatch diagnostics khác, nên không chuyển nguyên hành vi qua functional.

Nếu API yêu cầu rất chặt status 405/406/415:
1. Định nghĩa expected contract rõ ràng.
2. Test ma trận method/path/Content-Type/Accept qua HTTP server thật.
3. Bổ sung fallback/error handler/hạ tầng phù hợp nếu default khác mong muốn.
4. Không trả 200 cho malformed JSON hoặc route không chấp nhận media type chỉ để “dễ gọi API”.
5. Đừng mở catch-all route trước route cụ thể vì nó sẽ shadow các status chuyên biệt.

## 26. Debug routing khi kết quả bất ngờ

Quy trình chẩn đoán từ dễ đến khó:

1. Xác nhận application thực sự chạy **WebFlux** (Boot starter, application type, Reactor Netty) chứ không phải MVC.
2. Xác nhận `RouterFunction<ServerResponse>` được tạo thành Spring bean trong application context, không chỉ là biến local chưa đăng ký.
3. Kiểm HTTP method từ client (`GET` khác `POST`; HEAD/OPTIONS có đường xử lý riêng).
4. Kiểm path và thứ tự: static before variables, nested base path, trailing slash, context path, encoded separators.
5. Kiểm raw `Content-Type` và `Accept` thực sự gửi; client libraries thường tự thêm Accept hoặc content type.
6. Kiểm `headers(...)` custom predicate có so đúng name/value, missing header null.
7. Xác nhận `and`/`or`/`negate` biểu đạt đúng logic; `Accept: */*` có thể match nhiều routes.
8. Kiểm RouterFunctionMapping ordering khi app có nhiều router beans/annotated controllers.
9. Nếu route đã match mà body lỗi, kiểm handler `bodyToMono`, codecs, validation, `ServerResponse.contentType`.
10. Kiểm WebFilter/Spring Security/CORS có từ chối request trước router không.
11. Nếu response đã commit và stream lỗi, không thể luôn đổi status/body; log/cancel cleanup.
12. Dùng `WebTestClient` với request headers tường minh, không chỉ test qua browser đã cache/proxy.
13. Bật route mapping diagnostics ở test/staging có kiểm soát, không expose secrets.
14. Với redirects/proxy, kiểm trusted forwarded headers để tránh host/scheme/path sai.
15. So sánh cùng HTTP request qua direct Netty và ingress production khi nghi proxy rewrites.

### Anti-pattern: kiểm header trong handler thay vì routing

```java
.GET("/api/status", request -> {
    if ("trace".equals(
            request.headers().firstHeader("X-View"))) {
        return handler.status(request);
    }
    return ServerResponse.notFound().build();
})
```

Đây là snippet có thể làm, nhưng nếu ý định là *điều kiện chọn route*, dùng `headers(...)` sẽ thể hiện contract rõ hơn và cho phép fallback routes. **Không** dùng header predicate cho auth; cả hai cách đều cần security policy riêng.

## 27. Lỗi phổ biến

1. **Import MVC.fn package trong dự án WebFlux:** classes cùng tên nhưng khác reactive/servlet APIs.
2. **Định nghĩa RouterFunction nhưng không @Bean:** WebFlux không biết router.
3. **Đặt `/{id}` trước `/special`:** generic route nuốt request.
4. **Cho rằng functional routing tự chọn pattern cụ thể nhất:** thứ tự thắng.
5. **Đặt route GET không predicate trước GET có header predicate:** route có header không bao giờ tới.
6. **Nhầm Content-Type với Accept:** một cái mô tả body request, cái kia mô tả response chấp nhận.
7. **So literal header Accept bằng equals:** wildcard/quality/media compatibility không được xử lý.
8. **Tin Content-Type JSON bảo đảm JSON hợp lệ:** cần decoder và validation.
9. **Chỉ route theo Content-Type nhưng trả response body loại khác Accept:** client có thể không xử lý.
10. **Không set response contentType khi cần JSON/SSE:** codec/media mismatch.
11. **Dùng header X-Role cho auth:** header client tự khai dễ giả mạo.
12. **Tin HTTP 415/406 luôn xuất hiện khi predicate false:** router có thể chỉ xem là no-match.
13. **Không test POST method mismatch:** 405/404/OPTIONS khác tùy stack.
14. **Không test HEAD/OPTIONS/CORS:** browser có thể gửi preflight trước request thật.
15. **Không validate path variable:** ID có thể sai format và tạo resource traversal.
16. **Tự decode URI path một lần nữa:** có thể đổi dữ liệu thành separator.
17. **Dùng route pattern chứa wildcard rộng và đặt trước protected route:** shadow security/matching.
18. **Đặt nested accept(JSON) cho cả text POST:** text branch bị loại trước khi tới.
19. **Viết custom RequestPredicate gọi JDBC/block:** chặn reactive event loop.
20. **Tự subscribe trong HandlerFunction:** tách completion/error/cancel khỏi HTTP.
21. **Gọi block() trong Netty event loop:** throughput giảm hoặc Reactor ném lỗi.
22. **Dùng contentType(JSON) cho GET body rỗng:** có thể loại bỏ request hợp lệ.
23. **Không giới hạn request body trước decode:** memory/CPU pressure.
24. **Chấp nhận malformed JSON và trả 200 empty:** che lỗi validation.
25. **Không phân biệt query parameter và header predicate:** metadata khác nhau.
26. **Tạo nhiều RouterFunction beans trùng route không kiểm @Order:** route bị chọn tùy order.
27. **Tin client luôn gửi Accept cụ thể:** nhiều clients gửi `*/*`.
28. **Hardcode JSON property order/stdout timestamp trong tests:** flaky/unnecessary.
29. **Cho rằng mỗi SSE element là một packet:** network framing khác message boundaries.
30. **Không cleanup trên client disconnect:** giữ event subscriptions/timers.
31. **Coi response 201 là đã persist thật:** demo không có database.
32. **Không kiểm authenticated principal/resource permission sau route match:** route match không cấp quyền.
33. **Chuyển 404 thành catch-all 200 cho API lạ:** giấu lỗi client.
34. **Tin routing theo path xử lý toàn bộ nội dung encode:** cần canonicalization/URL-safe IDs.
35. **Lẫn RouterFunctionMapping với RequestMappingHandlerMapping:** functional và annotated không có cùng route precedence.
36. **Sửa SPI WebFlux chỉ để thêm một GET/POST route:** builder đã đủ.
37. **Dùng header metadata để đoán tenant đáng tin:** tenant phải đến từ trusted identity/authorization.
38. **Không test content negotiation đa representation:** Accept wildcard tạo ambiguity.

## 28. Checklist production và code review

### Routing

- [ ] Dùng `org.springframework.web.reactive.function.server` đúng stack WebFlux?
- [ ] Có `@Bean RouterFunction<ServerResponse>` được Boot nhận diện?
- [ ] Path tĩnh đặt trước path variables/generic wildcard?
- [ ] Nested path prefixes không bị lặp/trùng slash ngoài ý muốn?
- [ ] Method route khớp API contract (GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS)?
- [ ] Header predicates ngắn, pure và không dùng làm authentication?
- [ ] `contentType` dùng cho loại request body, `accept` cho response?
- [ ] Các predicates `and/or/negate` có test riêng?
- [ ] Không có routes shadow nhau khi client gửi `Accept: */*`?
- [ ] Multiple RouterFunction beans có order rõ nếu overlapping?

### HTTP result và bảo mật

- [ ] `ServerResponse` đặt status và response Content-Type đúng?
- [ ] Body readers/codecs parse JSON/form/multipart theo đúng media type?
- [ ] Body size/validation/authorization được kiểm sau route match?
- [ ] Không gọi blocking IO/`block()`/tự `subscribe()` trong handler?
- [ ] Không tin custom header hay path ID làm authenticated identity?
- [ ] Spring Security/CORS/CSRF policy tương ứng với functional routes?
- [ ] Response committed/stream cancellation/error có cleanup?
- [ ] Không log token, cookies hoặc raw query có secrets?

### Kiểm thử

- [ ] Test static `/special` thắng generic `/{id}`?
- [ ] Test POST JSON và POST text với Content-Type/Accept tường minh?
- [ ] Test header present/absent/wrong value?
- [ ] Test wildcard Accept, text/json swapped và wrong HTTP method?
- [ ] Test 400 malformed/empty body và domain-invalid fields?
- [ ] Test unknown path/no match, nested route và trailing slash?
- [ ] Test trên WebTestClient + HTTP server thật để thấy error pipeline?
- [ ] Test qua proxy/gateway nếu có path rewrites hoặc forwarded headers?
- [ ] Test SSE events và cancellation khi streaming được dùng?

## 29. Câu hỏi tự kiểm tra

**1.** `RouterFunction` khác `HandlerFunction` thế nào?

**Đáp án:** RouterFunction chọn handler bằng predicates, HandlerFunction xử lý request và trả Mono<ServerResponse>.

**2.** Vì sao `GET("/books/{id}")` nên đứng sau `GET("/books/special")`?

**Đáp án:** Functional routes được xét theo thứ tự; generic route có thể match “special” như một id, không tự chọn pattern cụ thể nhất.

**3.** `contentType(APPLICATION_JSON)` kiểm gì?

**Đáp án:** Loại **request body** client gửi, không phải loại body server sẽ trả.

**4.** `accept(APPLICATION_JSON)` kiểm gì?

**Đáp án:** `Accept` cho representation client có thể nhận.

**5.** `ServerResponse.contentType(APPLICATION_JSON)` có thay thế predicate `accept(JSON)` không?

**Đáp án:** Không. Nó xác định representation/codec của response, còn predicate dùng trong chọn route.

**6.** Header `X-Role: ADMIN` có thể dùng làm điều kiện quyền không?

**Đáp án:** Không; client tự khai được. Spring Security và business authorization mới quyết định quyền.

**7.** `and` và `or` trong RequestPredicate khác gì?

**Đáp án:** `and` yêu cầu cùng đúng, `or` chỉ cần một đúng; đặt thứ tự và test composition.

**8.** Request `Accept: */*` match những route nào?

**Đáp án:** Có thể match nhiều representations tương thích; functional route order quyết định khi nhiều match.

**9.** Khi gửi Content-Type text/plain tới route chỉ nhận JSON, status chắc chắn là 415?

**Đáp án:** Không thể kết luận chỉ từ predicate false. Nó có thể thành no-match tùy hạ tầng; HTTP contract cần được test/cấu hình.

**10.** Có thể vừa dùng annotated controllers vừa functional routes không?

**Đáp án:** Có, cùng WebFlux DispatcherHandler nhưng mapping/adapter/result handlers khác. Tránh overlap ngoài ý muốn.

**11.** Dùng `@RequestBody` trong HandlerFunction có đúng không?

**Đáp án:** Functional model dùng `ServerRequest.bodyToMono(...)` hoặc `bodyToFlux(...)`, không dùng method parameter annotations kiểu controller.

**12.** Một HandlerFunction cần tự gọi `Mono.subscribe()` để ghi body?

**Đáp án:** Không. Trả Mono<ServerResponse> cho WebFlux HTTP infrastructure.

**13.** Khi nào nên dùng `.path(prefix, builder)`?

**Đáp án:** Khi nhiều routes dùng chung path prefix, ví dụ `/api/books`; vẫn cần thứ tự specific-before-general bên trong.

**14.** Vì sao route match chưa đủ để trả 200?

**Đáp án:** Body có thể hỏng, validation fail, thiếu authorization, codec không hỗ trợ hoặc downstream error.

**15.** Khi nào dùng WebTestClient.bindToRouterFunction?

**Đáp án:** Khi muốn test router/handler logic nhanh không mở server, bổ sung HTTP integration tests để bao phủ security/filter/transport.

## 30. Tài liệu tham khảo

- Spring Framework 6.2 — Functional Endpoints (WebFlux.fn) và thứ tự routes/nested/predicates: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html
- Spring Framework 6.2 — `RequestPredicates` (reactive API Javadoc): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicates.html
- Spring Framework 6.2 — `RouterFunctions.Builder` (reactive API Javadoc): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.Builder.html
- Spring Framework 6.2 — `ServerRequest` (reactive API Javadoc): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html
- Spring Framework 6.2 — `ServerResponse` (reactive API Javadoc): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html
- Spring Framework 6.2 — DispatcherHandler and WebFlux routing SPI: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html
- Spring Framework — Path Patterns: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security — Reactive/WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/index.html
- Reactor Core Reference — reactive lifecycle, backpressure and schedulers: https://projectreactor.io/docs/core/release/reference/
- RFC 9110 — HTTP Semantics, Accept, Content-Type, status codes and methods: https://www.rfc-editor.org/rfc/rfc9110.html

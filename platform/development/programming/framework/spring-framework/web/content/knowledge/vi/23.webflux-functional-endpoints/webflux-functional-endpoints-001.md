# WebFlux.fn, RouterFunction và HandlerFunction trong Spring WebFlux

> **Phạm vi:** Functional WebFlux (WebFlux.fn), Spring Framework 6.2.x và Spring Boot 3.5.x, Java 17+. Bài giải thích `RouterFunction<ServerResponse>`, `HandlerFunction<ServerResponse>`, `ServerRequest`, `ServerResponse`, request predicates, route composition/nesting/filtering, cách đọc và ghi body reactive, validation và HTTP errors, kiểm thử `WebTestClient`, bảo mật và hiệu năng. Có một ứng dụng Spring Boot WebFlux có thể chạy độc lập. **Đừng nhầm với WebMvc.fn:** package của bài này là `org.springframework.web.reactive.function.server` và handler trả **`Mono<ServerResponse>`**, không phải `ServerResponse` đồng bộ.

## 1. WebFlux.fn là gì?

Spring WebFlux cung cấp hai mô hình khai báo HTTP endpoints:

1. **Annotated controllers:** dùng `@RestController`, `@GetMapping`, `@PostMapping`, `@RequestBody`.
2. **Functional endpoints (WebFlux.fn):** dùng các hàm nhận `ServerRequest` và trả `Mono<ServerResponse>`, ghép thành `RouterFunction<ServerResponse>` bằng Java DSL.

Cả hai cùng sử dụng **reactive WebFlux foundation**. Chúng không phải hai HTTP servers riêng biệt, và có thể cùng tồn tại trong một ứng dụng WebFlux. Khác biệt chủ yếu nằm ở cách **khai báo mapping và handler contract**, không nằm ở chuyện một bên có thể non-blocking còn bên kia thì không.

Ví dụ đối chiếu:

```java
// Annotated WebFlux: framework đọc @GetMapping để đăng ký route.
@RestController
class AnnotatedHello {
    @GetMapping("/hello")
    Mono<String> hello() {
        return Mono.just("Hello");
    }
}
```

```java
// Functional WebFlux: route và function được khai báo trực tiếp.
// Snippet trong class @Configuration với @Bean và imports phù hợp.
@Bean
RouterFunction<ServerResponse> helloRoutes() {
    return RouterFunctions.route()
            .GET("/hello", request ->
                    ServerResponse.ok().bodyValue("Hello"))
            .build();
}
```

Nếu đặt **cả hai routes cùng `GET /hello`** vào một ứng dụng, việc chọn handler có thể phụ thuộc mapping order/registration và gây xung đột về contract. Đây là hai **phương án thay thế**, không nên copy đồng thời cho cùng URL/method mà thiếu kế hoạch.

**Ghi nhớ hai kiểu hàm quan trọng:**

```java
// HandlerFunction<ServerResponse>:
ServerRequest -> Mono<ServerResponse>

// RouterFunction<ServerResponse>:
ServerRequest -> Mono<HandlerFunction<ServerResponse>>
```

Hình thức thứ hai cho thấy một router **không xử lý body**; nó chọn handler khi request phù hợp, hoặc trả Mono rỗng nếu không match. Trong phần lớn ứng dụng, ta không tự implement interfaces mà dùng `RouterFunctions.route()`/builder và method references.

## 2. Sơ đồ request đi qua WebFlux.fn

```text
Browser / mobile / service client
             |
      HTTP request bytes
             |
       Reactor Netty
             |
     HttpHandler + WebFilter chain
             |
      DispatcherHandler
             |
   RouterFunctionMapping
             |
  RouterFunction<ServerResponse>
    |       |       |
 predicate? |       +-> route khác
    |       |
    | match v
    +--> HandlerFunctionAdapter
                  |
        HandlerFunction.handle(ServerRequest)
                  |
            Mono<ServerResponse>
                  |
        ServerResponseResultHandler
                  |
        HttpMessageWriter / codecs
                  |
         HTTP response bytes
```

Trong ứng dụng Spring Boot dùng WebFlux starter, hạ tầng WebFlux đăng ký:
- **`RouterFunctionMapping`:** tìm các bean `RouterFunction<?>` và tổng hợp routes có thứ tự.
- **`HandlerFunctionAdapter`:** gọi `HandlerFunction` đã được chọn.
- **`ServerResponseResultHandler`:** ghi `ServerResponse` vào HTTP response.

Thông thường không cần tự gọi `RouterFunctions.toHttpHandler(...)` hoặc tự khởi tạo `DispatcherHandler`; đó là khả năng dùng WebFlux.fn với adapter/server tự cấu hình hoặc trường hợp nâng cao.

### 2.1. Vì sao tính bất biến hữu ích?

`ServerRequest` và `ServerResponse` có hợp đồng giao diện theo hướng bất biến. Handler có thể trả một mô tả phản hồi mà không trực tiếp ghi socket bằng lệnh imperative:

```java
HandlerFunction<ServerResponse> handler =
        request -> ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("Hello WebFlux.fn");
```

Framework điều phối body writers và subscription. Việc **xây dựng pipeline** không đồng nghĩa toàn bộ business work đã được thực hiện; publishers thường lazy và chỉ hoạt động khi được subscribe.

Bất biến của request/response abstraction **không** có nghĩa code bên trong handler không có side effects; database writes, email, transaction và shared state vẫn cần được kiểm soát.

## 3. API cốt lõi: bốn thành phần

| Thành phần | Vai trò | Kiểu hoặc API quan trọng |
| --- | --- | --- |
| `RouterFunction<ServerResponse>` | Ghép request vào handler | `RouterFunctions.route()`, `andOther(...)` |
| `HandlerFunction<ServerResponse>` | Xử lý request và tạo response bất đồng bộ | `Mono<ServerResponse> handle(ServerRequest)` |
| `ServerRequest` | Đọc method/URI/path variables/query/headers/cookies/body | `pathVariable`, `queryParam`, `bodyToMono`, `bodyToFlux` |
| `ServerResponse` | Xây status, headers và body reactive | `ok`, `created`, `notFound`, `bodyValue`, `body`, `build` |
| `RequestPredicate` | Điều kiện một route có được chọn | `path`, `method`, `accept`, `contentType` |
| `HandlerFilterFunction` | Bao quanh handler được match | `filter((request,next) -> ...)` |
| `WebFilter` | Lớp HTTP filter ở WebFlux infrastructure | Authentication/tracing/CORS phù hợp |

Một route không nhất thiết cần class handler. Với endpoint rất đơn giản, lambda có thể là đủ:

```java
RouterFunction<ServerResponse> ping = RouterFunctions.route()
        .GET("/ping",
                request -> ServerResponse.ok().bodyValue("pong"))
        .build();
```

Khi có nhiều chức năng, tách business logic vào một `@Component` handler class giúp kiểm thử và duy trì tốt hơn.

## 4. RouterFunction: chọn đường dẫn và method

### 4.1. Khai báo nhiều routes

```java
@Bean
RouterFunction<ServerResponse> itemRoutes(ItemHandler handler) {
    return RouterFunctions.route()
            .GET("/api/items", handler::list)
            .GET("/api/items/{id}", handler::get)
            .POST("/api/items", handler::create)
            .PUT("/api/items/{id}", handler::replace)
            .DELETE("/api/items/{id}", handler::delete)
            .build();
}
```

Đây là **snippet bean** cần `ItemHandler` và imports. Lưu ý handler methods đều có chữ ký ý tưởng:

```java
public Mono<ServerResponse> get(ServerRequest request) {
    // xử lý body/status không blocking
}
```

Các shortcut `GET`/`POST` của builder đã bao gồm HTTP method predicate, và path tương ứng.

### 4.2. Routes được xét theo thứ tự

Một khác biệt rất quan trọng: **WebFlux.fn đánh giá routes theo thứ tự được khai báo**. Nếu route trước match, nó chọn handler trước khi xét route sau. Vì vậy, route cụ thể nên đứng trước route tổng quát:

```java
return RouterFunctions.route()
        .GET("/api/items/popular", handler::popular)
        .GET("/api/items/{id}", handler::getById)
        .build();
```

Nếu đảo thứ tự và `/{id}` đứng trước, literal `popular` có thể bị coi là ID. Với annotated controllers, framework dùng mapping comparator để chọn mapping cụ thể nhất theo điều kiện; đừng mặc định WebFlux.fn tự đổi thứ tự các route của bạn cho giống annotations.

### 4.3. RequestPredicate

`RequestPredicates` có builders cho method, path, accept, content-type và các điều kiện khác:

```java
import static org.springframework.web.reactive.function.server.RequestPredicates.accept;
import static org.springframework.http.MediaType.APPLICATION_JSON;

return RouterFunctions.route()
        .GET("/api/items", accept(APPLICATION_JSON), handler::list)
        .build();
```

Hai predicates có thể được kết hợp bằng `and`, `or` hoặc `negate` khi thực sự cần logic phức tạp. Ví dụ:

```java
RequestPredicate jsonPost = RequestPredicates
        .method(HttpMethod.POST)
        .and(RequestPredicates.path("/api/items"))
        .and(RequestPredicates.contentType(MediaType.APPLICATION_JSON));
```

Đây là fragment cần `HttpMethod`/`MediaType` imports. Nếu predicate `contentType(APPLICATION_JSON)` không match, route có thể bị bỏ qua và trả 404 hay do mapping khác xử lý; **không tự mặc định** rằng predicate mismatch luôn tạo **415** giống tình huống decoder không hỗ trợ content type. Nếu API cần 415/406 chính xác, hãy kiểm thử và thiết kế error handling.

### 4.4. Nested routes và prefix

Thay vì lặp `/api/items`:

```java
return RouterFunctions.route()
        .path("/api/items", b -> b
                .GET("", handler::list)
                .GET("/{id}", handler::get)
                .POST("", handler::create))
        .build();
```

Nested route có thể chia sẻ path prefix hoặc predicate khác. Trong trường hợp nested `accept(JSON)`, ta có thể áp điều kiện chỉ cho nhóm GET mà không ảnh hưởng POST:

```java
return RouterFunctions.route()
        .path("/api/items", b -> b
                .nest(RequestPredicates.accept(MediaType.APPLICATION_JSON),
                        get -> get
                                .GET("", handler::list)
                                .GET("/{id}", handler::get))
                .POST("", handler::create))
        .build();
```

Ví dụ trên là snippet; routes GET yêu cầu Accept phù hợp JSON, trong khi POST không nhận cùng predicate này. Filter nằm bên trong nested builder chỉ có scope đến routes trong nested group; filter trên outer builder có thể bao toàn bộ các routes được xây dựng ở outer level.

### 4.5. Ghép nhiều RouterFunction

Ngoài builder `.add(otherRoute)`, RouterFunction còn hỗ trợ kết hợp bằng `and(...)`/`andOther(...)` tùy generic type. Khi khai báo nhiều RouterFunction beans, `RouterFunctionMapping` thu thập và sắp thứ tự. Trong ứng dụng lớn cần tổ chức thứ tự có chủ đích (ví dụ `@Order`) để route fallback/catch-all không nuốt routes của module khác. Không tự xem thứ tự bean scan hay thứ tự tên class là contract routing ổn định.

### 4.6. Static resources

`RouterFunctions.resources(...)` có thể ghép route phục vụ static resources. Đừng dùng một catch-all route rất rộng trước API routes; nó có thể làm lỗi API bị trả nhầm resource/static response. Với file upload/download, cần path canonicalization, permissions, MIME và header security; phục vụ resource không đồng nghĩa cho phép client chọn đường dẫn filesystem tùy ý.

## 5. HandlerFunction: nhiệm vụ đọc và trả response

Một handler function không được annotation `@GetMapping` gắn trực tiếp lên method; RouterFunction đã làm nhiệm vụ routing:

```java
@Component
class GreetingHandler {
    Mono<ServerResponse> hello(ServerRequest request) {
        String name = request.queryParam("name").orElse("guest");
        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("Hello " + name);
    }
}
```

Đây là snippet; cần imports. Khi route gọi `handler::hello`, giá trị nhận là `ServerRequest`, không phải một loạt tham số tự resolve bằng `@PathVariable`, `@RequestBody` như annotated controller method. **Handler phải lấy các dữ liệu đó từ `ServerRequest` một cách tường minh**.

### 5.1. Không return ServerResponse trực tiếp

Một trong các lỗi khi chuyển từ WebMvc.fn:

```java
// Sai với HandlerFunction của WebFlux.fn:
ServerResponse get(ServerRequest request) { ... }

// Đúng trong WebFlux.fn:
Mono<ServerResponse> get(ServerRequest request) { ... }
```

Thay thế chỉ bằng `Mono.just(serverResponse)` có thể chưa đủ trong handler có nguồn reactive: việc chọn status/body thường phụ thuộc kết quả `Mono<T>`. Cần composition thích hợp:

```java
return service.find(id)
        .flatMap(found -> ServerResponse.ok().bodyValue(found))
        .switchIfEmpty(ServerResponse.notFound().build());
```

Khi `find(id)` là Mono rỗng, method trả 404; không cần `block()` và không tự subscribe.

### 5.2. Một handler lambda hay class riêng?

| Cách | Phù hợp | Điểm cần lưu ý |
| --- | --- | --- |
| Lambda ngay trong route | Ping, hello, endpoint rất ngắn | Đừng biến RouterFunction bean thành một controller dài khó test |
| Method reference trong component | REST domain, nhiều endpoints | Có thể inject service, tách unit test |
| HandlerFunction implements riêng | Custom behavior hoặc composition | Đừng viết nhiều boilerplate nếu method reference đủ |

Dù dùng class, business logic nên ở service/repository thay vì nhồi DB transactions vào router declaration.

## 6. ServerRequest: URI, query, path và headers

`ServerRequest` cung cấp các API gần HTTP semantics:

```java
String id = request.pathVariable("id");
String query = request.queryParam("q").orElse("");
String method = request.method().name();
URI uri = request.uri();
List<MediaType> accept = request.headers().accept();
Optional<MediaType> contentType = request.headers().contentType();
String trace = request.headers().firstHeader("X-Trace-Id");
```

Đây là snippet, cần imports `java.net.URI`, `java.util.*` và `MediaType`. Các API query/cookie/headers có typed variants; hãy dùng chúng thay cho parser tự viết nếu khớp yêu cầu.

### 6.1. Parse path variable và lỗi

```java
long id;
try {
    id = Long.parseLong(request.pathVariable("id"));
} catch (NumberFormatException ex) {
    return ServerResponse.badRequest()
            .bodyValue(new ApiError("invalid_id"));
}
```

Đây là ví dụ trong một handler có return `Mono<ServerResponse>`; cần DTO `ApiError`. Tránh để `NumberFormatException` thành 500 và đừng phơi nội dung exception thô ra client. Trong code runnable bên dưới, route-level `onError(IllegalArgumentException.class,...)` giúp trả 400 khi ID không hợp lệ.

### 6.2. Query param nhiều giá trị

`request.queryParam("tag")` lấy một giá trị tùy API contract, còn request có thể chứa `?tag=a&tag=b`. Nếu API cho phép nhiều tags, xem `request.queryParams()` (`MultiValueMap<String,String>`) và định nghĩa rõ semantics OR/AND/deduplication/maximum count. Không ngầm chuyển các tham số lọc/search thành SQL string không có binding.

### 6.3. Header không phải security authority

`request.headers().firstHeader("X-User-Role")` chỉ đọc header do client có thể gửi. Nó **không** có tác dụng chứng minh người gọi là admin. Dùng reactive Spring Security `SecurityWebFilterChain` và quyền truy cập theo resource/tenant. Nếu cần principal:

```java
Mono<Principal> principal = request.principal();
```

`request.principal()` là async Mono; nếu API cần phân biệt anonymous user, phải xử lý empty theo contract và reactive SecurityContext đúng cách. Không tin raw `X-Forwarded-*` để xác định identity hay build redirects trừ khi trusted proxy đã scrub/normalize.

## 7. Đọc request body reactive

### 7.1. Một JSON object: bodyToMono

Với POST JSON:

```http
POST /api/books HTTP/1.1
Content-Type: application/json

{"title":"Spring WebFlux"}
```

Handler có thể dùng:

```java
Mono<CreateBook> input = request.bodyToMono(CreateBook.class);
```

Reader/codec (thường Jackson JSON) dùng media type và Java target type để decode bytes thành DTO. **Publisher là lazy**, nên việc gọi `bodyToMono(...)` không yêu cầu đọc toàn body ngay tại thời điểm tạo biến; WebFlux quản lý subscription và backpressure.

Không gọi:

```java
// ANTI-PATTERN: tránh block event-loop.
CreateBook input = request.bodyToMono(CreateBook.class).block();
```

Thay bằng compose:

```java
return request.bodyToMono(CreateBook.class)
        .flatMap(service::create)
        .flatMap(saved -> ServerResponse
                .created(URI.create("/api/books/" + saved.id()))
                .bodyValue(saved));
```

Đoạn là snippet; `service.create` trả `Mono<Book>` và cần URI/import. Cần áp validation trước khi ghi.

### 7.2. Nhiều values: bodyToFlux

```java
Flux<CreateBook> commands = request.bodyToFlux(CreateBook.class);
```

Nếu request là NDJSON hoặc streaming media type tương thích, body có thể được decode theo từng phần tử. Với JSON array, codec có thể decode nhiều values theo quy tắc media type/codec version. **Không** giả định mọi Content-Type đều hỗ trợ streaming từng record với cùng semantics.

Một ví dụ xử lý từng item:

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(
                request.bodyToFlux(CreateBook.class)
                        .concatMap(service::create),
                Book.class);
```

Đây là snippet: cần codec hỗ trợ `application/x-ndjson`, `service.create` trả Mono<Book>, và contract cho phép trả records theo dòng. `concatMap` giữ thứ tự inner writes; `flatMap` có thể tăng concurrency nhưng đổi thứ tự. Cần hard limits trên số phần tử và kích thước request, chứ không dùng stream vô hạn không kiểm soát.

### 7.3. Generic type

Khi cần body là `List<CreateBook>` trong một JSON array:

```java
Mono<List<CreateBook>> batch = request.bodyToMono(
        new ParameterizedTypeReference<List<CreateBook>>() {});
```

Java type erasure khiến `List.class` không mang generic element type; typed reference cho Jackson biết các phần tử phải là `CreateBook` thay vì raw map. Mặc dù generic metadata đúng, bạn vẫn phải giới hạn số phần tử và kích thước payload.

### 7.4. Không đọc cùng body hai lần

Một reactive request body thường là stream được consume theo lifecycle HTTP. Anti-pattern:

```java
request.bodyToMono(String.class).subscribe(System.out::println);
return request.bodyToMono(CreateBook.class)
        .flatMap(service::create)
        .flatMap(ServerResponse.ok()::bodyValue);
```

Subscription tự tạo đã tách khỏi response lifecycle, đồng thời lần đọc thứ hai không được đảm bảo có cùng dữ liệu. Đối với logging/auditing, dùng bounded request-body decorator/observability được thiết kế đúng; không chép nguyên JWT/PII/raw body vào logs.

### 7.5. Validation tách khỏi deserialization

JSON codec chỉ biến bytes thành DTO; không có nghĩa `title` hợp lệ hoặc caller được phép ghi. Một manual rule:

```java
private static void validate(CreateBook input) {
    if (input == null || input.title() == null
            || input.title().isBlank()
            || input.title().length() > 120) {
        throw new IllegalArgumentException("Invalid title");
    }
}
```

Nếu dùng Jakarta Bean Validation/`@Validated`, trong functional handler phải áp Validator có chủ đích; không dựa vào tự động `@Valid @RequestBody` của annotated controller method. Spring reference minh họa `Validator` + `BeanPropertyBindingResult` và `ServerWebInputException` cho 400. Cần DTO allowlist, không decode JSON trực tiếp vào JPA entity có fields như `role`, `ownerId`, `tenantId`.

## 8. ServerResponse: status, headers, body

### 8.1. 200 OK JSON body

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new Book(1L, "Spring"));
```

`bodyValue(Object)` dành cho value đã có; trả `Mono<ServerResponse>`, framework encode body qua `HttpMessageWriter`. Với DTO `Book` từ demo, JSON thường là:

```json
{"id":1,"title":"Spring"}
```

### 8.2. 201 Created + Location

```java
return ServerResponse
        .created(URI.create("/api/books/42"))
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new Book(42L, "Spring"));
```

Location URI có thể tương đối; nếu cần absolute canonical links, không ghép raw `Host`/`X-Forwarded-Host` của client thành external URL không tin cậy.

### 8.3. 204 No Content

```java
return ServerResponse.noContent().build();
```

HTTP 204 không có response body. Dùng cho delete/update thành công khi không cần trả resource mới. Nếu body cần hiển thị phiên bản mới, chọn 200 và JSON representation.

### 8.4. 400, 404, 409 với error DTO

```java
return ServerResponse.badRequest()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new ApiError("invalid_input"));
```

```java
return ServerResponse.notFound().build();
```

```java
return ServerResponse.status(HttpStatus.CONFLICT)
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new ApiError("conflict"));
```

Tình huống 409 có thể biểu thị business conflict, còn 412 phù hợp failed HTTP conditional request như `If-Match` stale version. Không trả HTTP 200 với `{"error":"not_found"}` nếu client cần dựa vào status code.

### 8.5. Header và cache

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .header("Cache-Control", "no-store")
        .header("X-Example", "webflux")
        .bodyValue(book);
```

Cache-Control phải phù hợp data sensitivity/authorization. Một header tùy biến không thay authentication. Tránh tự set `Content-Length` bằng Java `String.length()` vì ký tự Unicode và encoded bytes khác nhau.

### 8.6. Response body là Publisher

```java
Flux<Book> records = service.findAll();

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(records, Book.class);
```

Khác `bodyValue(book)`, `body(records, Book.class)` dùng Publisher và element type. **Đừng nhầm `bodyValue(flux)` với body Publisher.** Hãy dùng builder `body(Publisher, Class)` hoặc phù hợp `BodyInserter` cho source reactive.

### 8.7. SSE và NDJSON

```java
Flux<ServerSentEvent<String>> events = Flux.interval(
                Duration.ofSeconds(1))
        .take(3)
        .map(i -> ServerSentEvent.<String>builder()
                .id(i.toString())
                .event("tick")
                .data("event-" + i)
                .build());

return ServerResponse.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(events,
                new ParameterizedTypeReference<ServerSentEvent<String>>() {});
```

Snippet cần `Duration`, `ServerSentEvent`, `ParameterizedTypeReference` imports. SSE events có framing `event:`/`id:`/`data:` và kết thúc bằng dòng trống. Trong production, cần xử lý heartbeats, retries/resume IDs, proxy buffering, auth/tenant scope và client disconnect. Với `application/x-ndjson`, từng JSON value theo dòng; không tự kết luận đây là JSON array bình thường.

## 9. Reactive lifecycle, backpressure và non-blocking I/O

Trong WebFlux.fn, `ServerRequest.bodyToFlux(...)` và `ServerResponse.body(flux,...)` hỗ trợ **Reactive Streams backpressure**. Framework quản lý subscription khi đọc/ghi HTTP body. Nhưng reactive code vẫn có thể gây nghẽn khi:
- gọi JDBC/JPA blocking trên event-loop;
- gọi `Thread.sleep(...)` trong mapper;
- gọi `.block()` trong handler;
- tạo `Flux` vô hạn rồi `collectList()`;
- dùng `onBackpressureBuffer()` không giới hạn;
- thực thi nhiều downstream calls mà không đặt concurrency/connection limits.

### 9.1. Mono/Flux không tự làm code bất đồng bộ

```java
// Anti-pattern: work chạy ngay trước khi tạo Publisher.
Mono<Book> bad = Mono.just(legacyJdbc.findById(id));
```

`Mono.just(...)` nhận **giá trị đã tính xong**. Nếu code ở argument blocking, thread hiện tại vẫn bị block. Khi phải tích hợp blocking API tạm thời:

```java
Mono<Book> bridged = Mono.fromCallable(
                () -> legacyJdbc.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là snippet bọc blocking call có giới hạn; không biến JDBC thành reactive driver. Cân nhắc WebFlux + R2DBC, async WebClient hoặc Spring MVC khi app chủ yếu dùng blocking integrations.

### 9.2. Tránh tự subscribe trong handler

Handler nên **return publisher** để framework điều khiển cancellation/errors. Nếu tự `subscribe()` rồi trả response sớm, downstream error không còn gắn với HTTP request và thao tác có thể tiếp tục sau client disconnect. Đừng lấy `Mono<Void>` không có value làm lý do gọi `subscribe()` thủ công; có thể dùng `ServerResponse.ok().build(publisher)` để gắn completion với response khi phù hợp.

### 9.3. Streaming response đã committed

Khi SSE/NDJSON stream đã gửi header/body, một lỗi xảy ra muộn không đảm bảo đổi status 200 thành 500 hoặc thay response thành JSON error. Thiết kế protocol-level error event, close/cancel, reconnect/resume và logs/metrics riêng cho stream. Kiểm tra bằng HTTP client thực vì proxy/ingress có thể buffer các chunks.

## 10. Route filtering, before/after và onError

Functional router DSL có các chức năng:
- `before(Function<ServerRequest,ServerRequest>)`: thay đổi request abstraction trước handler, áp dụng trong scope builder.
- `after(BiFunction<ServerRequest,ServerResponse,ServerResponse>)`: hậu xử lý response trong scope.
- `filter(HandlerFilterFunction)`: bao quanh handler, quyết định có gọi `next.handle(request)` hay trả response sớm.
- `onError(...)`: chuyển exception phù hợp thành response.

### 10.1. Handler filter minh họa

```java
return RouterFunctions.route()
        .GET("/api/ping",
                request -> ServerResponse.ok().bodyValue("pong"))
        .filter((request, next) -> {
            long started = System.nanoTime();
            return next.handle(request)
                    .doOnSuccess(response -> {
                        long micros =
                                (System.nanoTime() - started) / 1000L;
                        System.out.println("responseBuiltMicros=" + micros);
                    });
        })
        .build();
```

Đây là snippet nhằm minh họa filter có thể bao quanh handler và đo thời điểm xây được `ServerResponse`. **Nó không đo đầy đủ thời gian ghi body/network**, vì response body có thể được stream sau đó. Production dùng Micrometer/Observation thay vì in stdout, không log raw headers/secrets.

### 10.2. Filter từ chối request

```java
.filter((request, next) -> {
    if (maintenanceModeEnabled()) {
        return ServerResponse.status(HttpStatus.SERVICE_UNAVAILABLE)
                .build();
    }
    return next.handle(request);
})
```

Đây là fragment; `maintenanceModeEnabled()` cần được định nghĩa. Không dùng một header do client tự đặt để quyết định quyền truy cập. Với authentication/authorization thật, dùng `SecurityWebFilterChain` và policy ở resource/service layer.

### 10.3. Nested filter scope

Nếu filter được thêm bên trong nested `path("/api/private", ...)`, scope không mặc định lan sang routes ở bên ngoài; một outer filter có thể bao các routes của outer builder. Do đó đặt auth controls hoàn toàn bằng một nested DSL filter dễ bỏ sót route mới. Security nên có global reactive filter chain và object-level authorization.

### 10.4. onError cho IllegalArgumentException

```java
return RouterFunctions.route()
        .GET("/api/books/{id}", handler::get)
        .onError(IllegalArgumentException.class,
                (ex, request) -> ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(new ApiError("invalid_input")))
        .build();
```

Đây là snippet route, không tự động bắt mọi lỗi từ WebFilter hoặc decoder trước routing. Catch type hẹp; không biến database failures thành 400. Nếu lỗi đã phát sau streaming response committed, onError cũng không thể đảm bảo thay status/header đã gửi.

### 10.5. before/after không thay security pipeline

Các DSL filters được gắn vào RouterFunction đã được match; WebFilter và Spring Security reactive filters nằm ở tầng HTTP handling rộng hơn. Nếu một router không match (hoặc request đến static resource/annotated controller), DSL filter gắn riêng router ấy không phải một security boundary tổng quát.

## 11. Cấu hình ServerRequest/ServerResponse codecs

WebFlux dùng `HttpMessageReader`/`HttpMessageWriter` reactive codecs. Các nội dung JSON trong demo phụ thuộc Jackson codec từ Boot WebFlux starter.

So sánh:

| Tác vụ | WebFlux.fn | WebMvc.fn |
| --- | --- | --- |
| Package | `web.reactive.function.server` | `web.servlet.function` |
| Handler return | `Mono<ServerResponse>` | `ServerResponse` |
| Read one JSON DTO | `request.bodyToMono(Dto.class)` | `request.body(Dto.class)` |
| Read stream | `request.bodyToFlux(Dto.class)` | Không có trực tiếp bodyToFlux |
| Write one value | `ServerResponse.ok().bodyValue(dto)` | `ServerResponse.ok().body(dto)` |
| Write Publisher | `body(publisher,Element.class)` | MVC có adapters nhưng write dựa trên Servlet |
| Codec | Reactive `HttpMessageReader/Writer` | `HttpMessageConverter` |
| I/O | Non-blocking reactive stack | Servlet blocking response writes |
| Async handling | Native Mono/Flux | Servlet async support nếu dùng reactive return |

**Không** chuyển import `org.springframework.web.servlet.function.ServerResponse` sang dự án WebFlux rồi thắc mắc vì sao `bodyValue`/`Mono<ServerResponse>` không khớp. Đây là **hai types khác nhau dù trùng tên**.

### 11.1. Codec buffer và kích thước payload

Spring Boot 3.5 có thể cấu hình:

```properties
spring.codec.max-in-memory-size=256KB
```

Đây là giới hạn bộ đệm codec cho các tình huống decode/aggregate, **không phải** hard cap cho tất cả HTTP bytes, file uploads hoặc mọi request streaming. Với JSON cực sâu, multipart lớn hoặc user gửi batch vô hạn, cần gateway/server/parser/stream quotas bổ sung. Không gom một Flux vô hạn bằng `collectList()`.

### 11.2. Content-Type, Accept và predicates

- Request `Content-Type` cho biết bytes body được gửi là JSON, text hay loại khác.
- Client `Accept` cho biết representation có thể nhận.
- `RequestPredicates.contentType(JSON)` hạn chế route theo Content-Type.
- `RequestPredicates.accept(JSON)` hạn chế route theo Accept.
- `ServerResponse.contentType(JSON)` khai báo media type phản hồi.

Nếu route predicate không match, HTTP status phụ thuộc phần còn lại của routing (có thể 404); nếu route đã match nhưng decoder không hỗ trợ input media type, thường có 415; nếu writer không tạo được output phù hợp, thường có 406/5xx tùy lỗi. Viết integration test cho contract 400/404/406/415 thay vì suy diễn từ một annotation dùng ở mô hình khác.

## 12. Demo runnable: Spring Boot 3.5, Java 17, WebFlux.fn

Demo tạo API sách bằng RouterFunction + HandlerFunction **không dùng `@RestController`**:

- `GET /api/books` — Flux các sách thành JSON array.
- `GET /api/books/{id}` — một sách JSON hoặc 404.
- `POST /api/books` — `bodyToMono(CreateBook.class)`, validate, tạo 201 + Location + JSON.
- `PUT /api/books/{id}` — cập nhật title hoặc 404.
- `DELETE /api/books/{id}` — 204 hoặc 404.
- `GET /api/books/ping` — route tĩnh phải khai báo trước `/{id}` để thể hiện order.

Store là in-memory `ConcurrentHashMap`, phục vụ demo routing/response; **không có database/authentication, CSRF, CORS, persistence, audit hay concurrency versioning**. Không đưa code này trực tiếp ra internet.

### 12.1. Khởi tạo Maven project

Tại [Spring Initializr](https://start.spring.io/), chọn Spring Boot **3.5.x**, Java **17+**, Maven, dependency **Spring Reactive Web**.

Fragment `pom.xml` do Initializr chuẩn bị:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
```

Dùng Spring Boot parent/BOM từ Initializr để quản lý versions của Reactor, Jackson, WebFlux và Netty. **Không thêm `spring-boot-starter-web` vào demo này**, vì Boot 3.x khi có cả MVC + WebFlux starters thường auto-configure Servlet MVC server. WebClient có thể được dùng trong MVC project, nhưng ở đây ta cần server thật sự là WebFlux.

Cấu trúc:

```text
src/main/
  java/com/example/demo/
    DemoApplication.java
src/test/
  java/com/example/demo/
    FunctionalBookTest.java
```

### 12.2. Toàn bộ Java source độc lập

Đặt **chính xác** nội dung sau vào `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.net.URI;
import java.util.Comparator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
        return RouterFunctions.route()
                // Route tĩnh trước route động.
                .GET("/api/books/ping", handler::ping)
                .GET("/api/books", handler::list)
                .GET("/api/books/{id}", handler::get)
                .POST("/api/books", handler::create)
                .PUT("/api/books/{id}", handler::replace)
                .DELETE("/api/books/{id}", handler::delete)
                .onError(IllegalArgumentException.class,
                        (ex, request) -> ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new ApiError("invalid_input")))
                .build();
    }
}

record Book(long id, String title) {}

record CreateBook(String title) {}

record ApiError(String error) {}

@Component
class BookHandler {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, Book> books =
            new ConcurrentHashMap<>();

    Mono<ServerResponse> ping(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("pong");
    }

    Mono<ServerResponse> list(ServerRequest request) {
        int limit = Integer.parseInt(
                request.queryParam("limit").orElse("20"));

        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("invalid limit");
        }

        Flux<Book> result = Flux.defer(() ->
                Flux.fromIterable(
                        books.values().stream()
                                .sorted(Comparator.comparingLong(Book::id))
                                .limit(limit)
                                .toList()));

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(result, Book.class);
    }

    Mono<ServerResponse> get(ServerRequest request) {
        long id = Long.parseLong(request.pathVariable("id"));

        return Mono.defer(() -> Mono.justOrEmpty(books.get(id)))
                .flatMap(book -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateBook.class)
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException("body required")))
                .flatMap(command -> {
                    validate(command);
                    return Mono.fromSupplier(() -> {
                        long id = nextId.incrementAndGet();
                        Book created = new Book(
                                id, command.title().trim());
                        books.put(id, created);
                        return created;
                    });
                })
                .flatMap(saved -> ServerResponse
                        .created(URI.create("/api/books/" + saved.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(saved));
    }

    Mono<ServerResponse> replace(ServerRequest request) {
        long id = Long.parseLong(request.pathVariable("id"));

        return request.bodyToMono(CreateBook.class)
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException("body required")))
                .flatMap(command -> {
                    validate(command);
                    return Mono.defer(() -> Mono.justOrEmpty(
                            books.computeIfPresent(
                                    id, (key, oldBook) ->
                                            new Book(
                                                    id,
                                                    command.title().trim()))));
                })
                .flatMap(updated -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(updated))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    Mono<ServerResponse> delete(ServerRequest request) {
        long id = Long.parseLong(request.pathVariable("id"));

        return Mono.fromSupplier(() -> books.remove(id) != null)
                .flatMap(deleted -> deleted
                        ? ServerResponse.noContent().build()
                        : ServerResponse.notFound().build());
    }

    private static void validate(CreateBook command) {
        if (command == null
                || command.title() == null
                || command.title().isBlank()
                || command.title().length() > 120) {
            throw new IllegalArgumentException("invalid title");
        }
    }
}
```

### 12.3. Giải thích tính runnable

- Java 17 hỗ trợ `record`; một file có đúng một public class `DemoApplication`, các top-level records/classes khác package-private hợp lệ.
- `@SpringBootApplication` và `@Component` phát hiện handler; method `@Bean RouterFunction<ServerResponse>` đăng ký functional routes.
- `RouterFunctions.route()` là WebFlux.fn, không phải WebMvc.fn vì imports bắt đầu bằng `org.springframework.web.reactive.function.server`.
- Methods `ping/list/get/create/replace/delete` đều trả `Mono<ServerResponse>`. Không dùng `.block()` hay detached `.subscribe()`.
- `request.bodyToMono(CreateBook.class)` decode JSON theo reactive HTTP codecs.
- `ServerResponse.ok().body(flux, Book.class)` cung cấp Publisher với element type để writer serialize thành response.
- `Mono.defer` và `Mono.fromSupplier` trì hoãn đọc/ghi in-memory cho đến subscription. **Chúng không làm mọi imperative code trở thành non-blocking**; demo chỉ dùng thao tác map rất nhanh, không có JDBC/disk/network blocking.
- `onError(IllegalArgumentException.class, ...)` trả 400 JSON cho lỗi parse path/query hoặc manual title validation trong phạm vi router này.
- JSON malformed/converter errors có exception type khác; không tự nhận rằng router `onError(IllegalArgumentException)` bắt mọi JSON parse error.
- `ConcurrentHashMap` + `AtomicLong` bảo đảm ID khác nhau trong một JVM, không cho độ bền dữ liệu hoặc multi-instance consistency.
- `PUT` không có `If-Match`/ETag; một stale client vẫn có thể overwrite. Production nên dùng optimistic locking.
- `GET /api/books/ping` đứng trước `GET /api/books/{id}` theo **thứ tự routing WebFlux.fn**.

### 12.4. Khởi chạy

Trong project root đã có Maven wrapper:

```bash
# Linux / macOS
./mvnw spring-boot:run

# Windows PowerShell/CMD
mvnw.cmd spring-boot:run
```

Nếu chưa cấu hình port, server thường nghe `http://localhost:8080`. Đây là Spring Boot WebFlux reactive application; không cần `@EnableWebFlux` để tạo handler mappings mặc định, và bật annotation này không cần thiết có thể ảnh hưởng auto-configuration.

### 12.5. Kiểm tra routes bằng curl

**Ping tĩnh:**

```bash
curl -i 'http://localhost:8080/api/books/ping'
```

Dự kiến status 200, `Content-Type` tương thích `text/plain`, body:

```text
pong
```

Nếu `/{id}` đặt trước trong router, `ping` có thể bị parse như ID, gây 400. Đây là minh họa rõ vì sao WebFlux.fn routing order quan trọng.

**List ban đầu:**

```bash
curl -i 'http://localhost:8080/api/books?limit=10'
```

Status 200, JSON array rỗng:

```json
[]
```

**POST tạo sách:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":"WebFlux Functional"}'
```

Nếu app vừa khởi động chưa tạo tài nguyên khác, status 201, Location và JSON tương ứng:

```http
HTTP/1.1 201 Created
Location: /api/books/1
Content-Type: application/json

{"id":1,"title":"WebFlux Functional"}
```

Status, Location và các JSON fields là điều cần kiểm tra; thứ tự headers, header Date, charset hay whitespace JSON do runtime/converter quyết định.

**GET theo ID:**

```bash
curl -i 'http://localhost:8080/api/books/1'
curl -i 'http://localhost:8080/api/books/9999'
```

Với ID 1 tồn tại: status 200 JSON. Với ID không tồn tại: 404.

**PUT title:**

```bash
curl -i -X PUT 'http://localhost:8080/api/books/1' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":"Updated title"}'
```

Khi ID tồn tại: status 200 JSON với title mới. Với ID không tồn tại: 404. Với title trống: 400 do validation.

**DELETE:**

```bash
curl -i -X DELETE 'http://localhost:8080/api/books/1'
```

Lần đầu nếu ID tồn tại: status 204 No Content. Lần tiếp theo cùng ID: 404 theo contract demo.

**Query limit lỗi:**

```bash
curl -i 'http://localhost:8080/api/books?limit=0'
curl -i 'http://localhost:8080/api/books?limit=abc'
```

Dự kiến 400 với JSON error DTO:

```json
{"error":"invalid_input"}
```

**Title lỗi:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":"  "}'
```

Dự kiến 400, `{"error":"invalid_input"}`. Với malformed JSON (ví dụ `{"title":`), việc decode thất bại sẽ được error infrastructure xử lý; **đừng giả định error body giống hệt manual validation** nếu chưa cấu hình chung.

### 12.6. Windows PowerShell

Dùng `curl.exe` thay vì `curl` alias để giữ cú pháp phổ biến:

```powershell
curl.exe -i "http://localhost:8080/api/books/ping"
curl.exe -i "http://localhost:8080/api/books?limit=10"
```

Với POST/PUT JSON, tạo file `request.json` UTF-8:

```json
{"title":"WebFlux Functional"}
```

Gửi:

```powershell
curl.exe -i -X POST "http://localhost:8080/api/books" -H "Content-Type: application/json" --data-binary "@request.json"
```

Cách này tránh escape-quote khác nhau giữa Bash, PowerShell 5 và PowerShell 7.

## 13. Kiểm thử WebFlux.fn bằng WebTestClient

Spring WebFlux có `WebTestClient` hỗ trợ bind-to-router-function hoặc gửi request qua embedded server thật. Để test end-to-end Spring Boot auto-configuration/codec/routes, dùng integration test với RANDOM_PORT.

### 13.1. Test dependency

Với Spring Boot 3.5, thêm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Trong Boot 4 starter/test auto-configuration packages đã được modular hóa, vì vậy cần kiểm tra lại dependency/import nếu nâng cấp; đoạn test dưới đây dành cho Boot 3.5.

### 13.2. File FunctionalBookTest.java

Lưu `src/test/java/com/example/demo/FunctionalBookTest.java`:

```java
package com.example.demo;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FunctionalBookTest {

    @Autowired
    WebTestClient client;

    @Test
    void staticRouteShouldNotBeCapturedAsNumericId() {
        client.get().uri("/api/books/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("pong");
    }

    @Test
    void createThenReadUsesRealLocation() {
        EntityExchangeResult<byte[]> created = client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":\"Test Book\"}")
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody()
                .jsonPath("$.title").isEqualTo("Test Book")
                .returnResult();

        URI location = created.getResponseHeaders().getLocation();
        assertNotNull(location);

        client.get().uri(location.toString())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Test Book");
    }

    @Test
    void unknownResourceReturns404() {
        client.get().uri("/api/books/999999")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void invalidTitleReturns400() {
        client.post().uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":\"   \"}")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("invalid_input");
    }

    @Test
    void invalidLimitReturns400() {
        client.get().uri("/api/books?limit=0")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

Test không hardcode ID=1 vì store có thể đã được tạo dữ liệu trong những tests khác cùng Spring context. `returnResult().getResponseHeaders().getLocation()` lấy URI thật từ 201 response, rồi GET URI đó. Test `/ping` bảo vệ thứ tự route tĩnh/động.

### 13.3. Test router đơn vị không khởi động server

Có thể dùng:

```java
WebTestClient client = WebTestClient
        .bindToRouterFunction(routerFunction)
        .build();
```

Đây là snippet; cần một `RouterFunction<ServerResponse> routerFunction` được tạo hoặc inject. Cách này test routing/handler mà không cần mở socket thật. Tuy nhiên không chứng minh proxy, Netty configuration, TLS, WebFilter/security chain production được áp đúng; kết hợp router-level tests với integration tests khi cần.

### 13.4. Chạy tests

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

Thêm test cho PUT/DELETE, wrong content type, malformed JSON, batch quá lớn, CORS/security, client disconnect và concurrency nếu chuyển store sang database. Với shared in-memory state, cần fixture isolation nếu tests chạy song song.

## 14. So sánh với WebMvc.fn và annotated WebFlux

| Tiêu chí | WebFlux.fn | WebMvc.fn | Annotated WebFlux |
| --- | --- | --- | --- |
| Router declaration | `RouterFunction` | `RouterFunction` | `@RequestMapping` |
| Handler | `Mono<ServerResponse> handle(ServerRequest)` | `ServerResponse handle(ServerRequest)` | Java method với annotated args/return |
| Request body | `bodyToMono/bodyToFlux` | `body(Class)/body(ParameterizedTypeReference)` | `@RequestBody Mono<Dto>` |
| Response body | `bodyValue/body(Publisher,Class)` | `body(Object)` | `Mono<Dto>`/`Flux<Dto>`/`ResponseEntity` |
| HTTP stack | Reactive WebFlux | Servlet MVC | Reactive WebFlux |
| Codec | `HttpMessageReader/Writer` | `HttpMessageConverter` | `HttpMessageReader/Writer` |
| Route ordering | **Khai báo trước được kiểm tra trước** | Functional routing theo order | Mapping comparator |
| Filter DSL | `before/after/filter/onError` | Có functional filters | @ControllerAdvice, WebFilter |
| HTTP I/O | Non-blocking khi runtime hỗ trợ | Servlet blocking writes | Non-blocking khi runtime hỗ trợ |
| Rõ ràng về route contract | DSL tập trung | DSL tập trung | Annotation nằm cạnh method |
| Controller argument binding | Tường minh qua ServerRequest | Tường minh qua ServerRequest | Framework resolve annotated params |

WebFlux.fn và annotated WebFlux có thể **cùng tồn tại** trong `DispatcherHandler`; nên tránh trùng path/method mà không có ownership routing rõ ràng. Nhiều teams thích annotated model cho CRUD đơn giản/Bean Validation mạnh, và WebFlux.fn cho gateways, route composition, filters hoặc handlers cần xây động. Không có mô hình nào “luôn nhanh hơn” chỉ vì cách khai báo; benchmark tập trung vào I/O, codecs, data access, thread/connection pools và backpressure.

### 14.1. Kotlin router DSL

Ngoài Java DSL, Spring hỗ trợ Kotlin `router { }` / `coRouter { }` (coroutines). Coroutine handlers có thể là `suspend fun` trả response với DSL riêng. **Không** chép trực tiếp các lời gọi `bodyValueAndAwait` từ Kotlin coroutine examples vào Java WebFlux.fn và kỳ vọng compile; Java dùng `Mono<ServerResponse>`.

### 14.2. Spring Framework 7 API versioning

Spring Framework 7 bổ sung khả năng version predicates/mappings có cấu hình API version strategy. **Không** dùng `RequestPredicates.version("1.0")` nếu codebase Spring Framework 6.2/Boot 3.5 chưa có API đó. Trên Spring 6.x, thực hiện version qua path/query/header/media type hoặc custom route policy được test rõ; khi nâng Spring 7 cần đọc tài liệu mới để biết supported versions/baseline/deprecation semantics.

## 15. CORS, Security và giao dịch

Functional routing là **cách chọn handler**, không phải security boundary.

### 15.1. Reactive Spring Security

Với WebFlux server, Spring Security sử dụng `SecurityWebFilterChain` và các reactive security context APIs. Khi viết business handler:
- xác thực người dùng theo token/cookie policy;
- authorize theo method/path và object ID/tenant;
- fail closed khi permission service không khả dụng;
- tránh log Authorization token;
- không coi `X-User-Role` hoặc `API-Version` là bằng chứng quyền.

Nếu app nhận cookies/session và có các thao tác state-changing, cần CSRF policy phù hợp. CORS origin allowlist cần tách biệt với authentication và không phản chiếu tùy ý mọi Origin kèm credentials.

### 15.2. CORS với WebFlux.fn

Spring reference mô tả CORS của functional endpoints qua `CorsWebFilter`. Một số cơ chế MVC annotations như `@CrossOrigin` gắn vào controller method **không phải** cấu hình CORS cho RouterFunction đã khai báo bằng DSL. Khi dùng Spring Security, CORS configuration phải phối hợp với reactive security filter chain và OPTIONS preflight; kiểm thử cross-origin từ client thật.

### 15.3. Giao dịch và consistency

WebFlux.fn không tự cấp database transaction. Dùng reactive transactional service/`TransactionalOperator` phù hợp với R2DBC nếu cần các thay đổi atomically; với external side effects cần outbox/saga/idempotency khi nghiệp vụ yêu cầu. Demo dùng in-memory map, không có transaction isolation giữa nhiều pods. Cũng không có ETag/If-Match để tránh lost update.

### 15.4. Upload/multipart

Đối với multipart, ServerRequest có thể truy cập parts qua reactive APIs; dùng `Part`/`FilePart` hoặc `PartEvent` streaming theo nhu cầu. Với `PartEvent`, cần consume/relay/release đầy đủ contents để tránh memory leaks. Không đọc file upload lớn vào một `byte[]` không giới hạn; phải có file size quota, file type validation, safe filename server-generated, scanning nếu policy yêu cầu và private storage.

## 16. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| IDE không tìm `bodyToMono` | Import WebMvc.fn ServerRequest | Dùng `web.reactive.function.server.ServerRequest` |
| Handler method báo sai return type | Dùng `ServerResponse` thay `Mono<ServerResponse>` | Compose và trả Mono |
| `bodyValue(flux)` không phù hợp | Truyền Publisher như plain value | Dùng `body(flux, Element.class)` |
| Route static `/ping` bị parse như ID | Route động `/{id}` đứng trước | Đặt route tĩnh trước |
| Hai routes trùng nhau | DSL order/registration không kiểm soát | Định nghĩa path/predicate rõ, tests |
| Route POST không match | `contentType` predicate/HTTP method/path sai | Test route với Content-Type |
| GET Accept chỉ XML không match JSON route | `accept(JSON)` false | Thống nhất media type, kiểm thử status |
| POST JSON lỗi trở thành 5xx | Không xử lý decoder/validation errors đúng | Error policy riêng cho parse/body |
| `Mono.empty()` trả response không đúng | Không mapping absence -> 404 | `switchIfEmpty(notFound().build())` |
| Handler tự `subscribe()` rồi response rỗng | Subscription tách HTTP lifecycle | Return Publisher |
| Handler dùng `block()` gây nghẽn | Blocking event loop | Compose Mono/Flux |
| Flux vô hạn không hoàn tất | Response JSON kiểu collect/buffer không có termination | Streaming media, timeout/quota |
| Client chậm gây memory pressure | Queue/buffer thiếu giới hạn | Backpressure, bounded buffers/concurrency |
| JSON generic ra List<Map> | Mất element type | `ParameterizedTypeReference` |
| Router filter không áp endpoint khác | Nested/router-local filter scope | Global WebFilter/security |
| CORS preflight bị từ chối | Chưa cấu hình CorsWebFilter/security | CORS chain đúng cho functional routes |
| Kết quả null từ Mono mapper | Reactor không cho null onNext | Dùng Mono.empty/justOrEmpty |
| JSON decode đúng nhưng dữ liệu vượt quyền | DTO/ACL thiếu | Validate và authorize |
| Header role spoofing | Tin X-User-Role từ client | Spring Security và tenant scope |
| 201 thiếu Location | Chỉ trả status 201 | `ServerResponse.created(uri)` |
| 204 có body | Dùng body trên noContent | `ServerResponse.noContent().build()` |
| Đã stream rồi muốn đổi status | Response committed | Stream error protocol/close |
| Có MVC và WebFlux starters, đang chạy MVC | Boot chọn Servlet MVC | Chọn web application stack rõ ràng |
| @EnableWebFlux làm mất Boot conventions | Can thiệp config không cần thiết | Giữ WebFlux Boot auto-config nếu đủ |
| Tests phụ thuộc ID=1 | Shared in-memory store | Dùng Location, fixture isolation |
| Malformed path id thành 500 | Parse không được map 400 | Narrow onError/manual parse |
| Data race khi nhiều writers | Map/DB update không có version | Optimistic locking/CAS |
| Proxy buffer SSE | Reverse proxy/HTTP client buffering | Test streaming end-to-end |

## 17. Checklist code review và vận hành

- [ ] Imports thuộc đúng `org.springframework.web.reactive.function.server`, không trộn WebMvc.fn.
- [ ] Có bean `RouterFunction<ServerResponse>` được Spring Boot phát hiện.
- [ ] Mỗi route có method/path/predicate rõ và theo **thứ tự tĩnh trước động**.
- [ ] Không có catch-all/fallback route vô tình che API khác.
- [ ] Handler return `Mono<ServerResponse>` và không gọi `block()` hoặc detached `subscribe()`.
- [ ] Request metadata đọc từ ServerRequest, body từ `bodyToMono/bodyToFlux` đúng codec.
- [ ] DTO và generic type đúng, không bind entity có trường server-managed.
- [ ] Validation/ACL và request body size/quota được áp dụng trước khi side effects.
- [ ] Response status, Content-Type, Location, Cache-Control, empty body semantics hợp lệ.
- [ ] Streaming SSE/NDJSON có timeout/heartbeat/cancel/reconnect và backpressure.
- [ ] onError/filter có scope rõ, không thay SecurityWebFilterChain.
- [ ] Global CORS preflight OPTIONS tương thích security, không phản chiếu Origin tùy ý.
- [ ] Không có JDBC/JPA blocking trực tiếp trên Netty event loop.
- [ ] Concurrency fan-out/gateway traffic có giới hạn; backpressure queues không vô hạn.
- [ ] Tests WebTestClient bao 200/201/204/400/404, invalid payload và thứ tự router.
- [ ] Với production writes có DB transactions, optimistic locking và idempotency.
- [ ] Monitoring có latency, 4xx/5xx, active requests, upstream errors, client disconnect mà không log secrets.
- [ ] Khi upgrade Spring Framework 7, rà soát request versioning và starter/test packages.

## 18. Câu hỏi ôn tập

**Câu 1.** WebFlux.fn khác WebMvc.fn về import và handler signature ra sao?

**Đáp án:** WebFlux.fn dùng `org.springframework.web.reactive.function.server`, handler nhận `ServerRequest` và trả `Mono<ServerResponse>`; WebMvc.fn dùng `org.springframework.web.servlet.function` và handler trả `ServerResponse`.

**Câu 2.** Tại sao đặt `GET /api/books/ping` trước `GET /api/books/{id}`?

**Đáp án:** WebFlux.fn kiểm tra routes **theo thứ tự**; route động có thể match literal `ping` nếu nó được đặt trước.

**Câu 3.** Đọc một JSON object thành CreateBook trong WebFlux.fn?

**Đáp án:** `request.bodyToMono(CreateBook.class)`, sau đó validate và compose kết quả bằng `flatMap`.

**Câu 4.** Trả Flux<Book> qua ServerResponse?

**Đáp án:** `ServerResponse.ok().contentType(APPLICATION_JSON).body(books,Book.class)`; không coi Flux là plain DTO cho `bodyValue`.

**Câu 5.** `Mono.empty()` có tự động mang nghĩa HTTP 404 không?

**Đáp án:** Không. Handler phải trả `ServerResponse.notFound().build()` hoặc xử lý absence rõ ràng.

**Câu 6.** Khi route filter gọi `next.handle(request)`, điều gì xảy ra?

**Đáp án:** Chuỗi handler/filter kế tiếp được chạy; nếu không gọi, filter có thể trả response sớm để chặn request.

**Câu 7.** `RequestPredicates.contentType(JSON)` false có bảo đảm 415 không?

**Đáp án:** Không. Router có thể đơn giản không match và đường xử lý lỗi phụ thuộc các routes khác; test nếu API cần 415.

**Câu 8.** Functional handler có tự chạy @Valid trên DTO mà bodyToMono decode không?

**Đáp án:** Không theo cùng cách annotated argument validation. Cần áp Validator/manual validation rõ.

**Câu 9.** Có thể dùng `@CrossOrigin` của annotated controller thay cho CorsWebFilter trên WebFlux.fn không?

**Đáp án:** Không mặc định; functional endpoints cần reactive CORS configuration tương ứng, thường thông qua `CorsWebFilter`.

**Câu 10.** WebFlux.fn đã non-blocking thì gọi JDBC trong `Mono.just(...)` có an toàn không?

**Đáp án:** Không. JDBC call chạy trước khi Mono.just được tạo và có thể block event loop; dùng reactive I/O hoặc controlled boundedElastic bridge/kiến trúc MVC phù hợp.

## 19. Tài liệu chính thức

- [Spring Framework 6.2 — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): RouterFunction/HandlerFunction/ServerRequest/ServerResponse, predicates, nested routes, filters, validation.
- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive HTTP foundation, non-blocking I/O, backpressure.
- [Spring Framework 6.2 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html): bodyToMono/bodyToFlux, query/path/header, multipart.
- [Spring Framework 6.2 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): response builder/status/body/headers.
- [Spring Framework 6.2 — RouterFunctions.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.Builder.html): GET/POST/nest/filter/onError methods.
- [Spring Framework 6.2 — RequestPredicates Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicates.html): method/path/accept/contentType composition.
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): Reactive HttpMessageReader/Writer foundation.
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): CorsWebFilter và bảo mật cross-origin.
- [Spring Boot 3.5 — Reactive Web](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): starter, RouterFunction beans và WebFlux server.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): WebTestClient integration testing.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): reactive SecurityWebFilterChain và access controls.
- [Project Reactor — Core Reference](https://projectreactor.io/docs/core/release/reference/): Mono/Flux, cancellation, scheduling, backpressure và tests.

**Kết luận:** WebFlux.fn biểu diễn routing bằng `RouterFunction<ServerResponse>` và behavior bằng `HandlerFunction<ServerResponse>`; mỗi handler nhận `ServerRequest` và trả **`Mono<ServerResponse>`**. Route matching được đánh giá theo thứ tự DSL; request bodies được đọc qua `bodyToMono/bodyToFlux`, response dùng `bodyValue` hoặc `body(Publisher,Class)`. Để vận hành an toàn, phải có DTO/validation/auth, giới hạn resource/concurrency, proper error handling và tests — không chỉ ghép lambda rồi cho rằng đã có một REST API production-ready.

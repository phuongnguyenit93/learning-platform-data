# ServerRequest, ServerResponse và hợp đồng bất đồng bộ trong Functional WebFlux

## 1. Functional WebFlux là gì và bài học giải quyết vấn đề nào?

Spring WebFlux có hai cách phổ biến để tạo HTTP endpoints: annotated controllers (`@RestController`, `@GetMapping`, `@RequestBody`) và **functional endpoints** hay **WebFlux.fn**. Ở WebFlux.fn, ta biểu diễn cách chọn route và cách xử lý request bằng các hàm Java, không cần gắn annotation lên từng HTTP handler.

Ba kiểu trung tâm thuộc package **`org.springframework.web.reactive.function.server`**:

- `ServerRequest` mô tả một HTTP request theo contract tiện dụng và immutable: method, path, URI, query, headers, path variables, cookies, body publishers.
- `HandlerFunction<T extends ServerResponse>` nhận một `ServerRequest` và trả **`Mono<T>`**, tức một publisher biểu diễn response được tạo **bất đồng bộ**.
- `ServerResponse` mô tả một HTTP response gồm status, headers, cookies và body. Builder cũng trả **`Mono<ServerResponse>`**.

Thành phần kết nối là `RouterFunction<T extends ServerResponse>`: nó lấy `ServerRequest` và trả một **`Mono<HandlerFunction<T>>`** nếu match; không match thì publisher complete empty. Trong ứng dụng bình thường ta không tự gọi router trên request từng lần mà đăng ký một `RouterFunction<ServerResponse>` Spring bean hoặc triển khai `HttpHandler`.

**Mục tiêu quan trọng nhất:** hiểu *hai hợp đồng bất đồng bộ khác nhau*:

1. **Routing phase:** `Mono<HandlerFunction<ServerResponse>>` — tìm handler khớp request; có thể empty khi không match.
2. **Handling phase:** `Mono<ServerResponse>` — sau khi match, handler có thể chờ dữ liệu reactive rồi tạo response với status/headers/body phù hợp.

Từ đó mới hiểu vì sao `Mono.empty()` của việc **không match route** khác với `Mono.empty()` của **không tìm thấy entity**, và vì sao response có thể chứa tiếp một `Flux<T>` body phát nhiều phần tử.

### 1.1. Kết quả học tập

Sau bài, bạn có thể:

1. Giải thích bằng chữ ký Java chuẩn: `ServerRequest → Mono<HandlerFunction> → Mono<ServerResponse>`.
2. Phân biệt WebFlux.fn với **WebMvc.fn** trên Servlet, không import lẫn package.
3. Đọc HTTP request bằng `pathVariable`, `queryParam`, `headers`, `bodyToMono` và `bodyToFlux`.
4. Dựng HTTP response 200/201/204/400/404/409/429; so `bodyValue`, `body(publisher, elementClass)` và `build()`.
5. Hiểu assembly, subscription, no-blocking, error/completion/cancellation, codec, backpressure và streaming media types.
6. Đăng ký `RouterFunctions.route()`, biết thứ tự first-match, `RequestPredicates`, nested/composed routes và `HandlerFilterFunction`.
7. Tách handler/service, bảo vệ validation, authentication, authorization, CORS, CSRF và tài nguyên dùng chung.
8. Có một dự án Spring Boot 3/Java 17 với CRUD reactive không có database, WebTestClient HTTP tests và Reactor StepVerifier tests.

**Phạm vi:** Spring Framework 6.x, Spring Boot 3.3.x, Project Reactor 3.x. Ví dụ chính chạy bằng **spring-boot-starter-webflux** trên Reactor Netty mặc định, không mang sang Spring MVC Servlet. Dự án dùng in-memory store để cô lập đúng nguyên lý WebFlux.fn; production dùng reactive database/HTTP clients với timeout và security thật.

## 2. So sánh hợp đồng với WebMvc.fn: cùng tên, khác bản chất

Một lỗi dễ mắc là dùng `org.springframework.web.servlet.function.ServerRequest` thay vì `org.springframework.web.reactive.function.server.ServerRequest`. Hai API có tên tương tự nhưng không thay thế được cho nhau.

| Điểm | WebMvc.fn (Servlet) | WebFlux.fn (Reactive) |
| --- | --- | --- |
| Package | `org.springframework.web.servlet.function` | `org.springframework.web.reactive.function.server` |
| HTTP infrastructure | `DispatcherServlet` | `DispatcherHandler` |
| Route result | `Optional<HandlerFunction<ServerResponse>>` | `Mono<HandlerFunction<ServerResponse>>` |
| Handler result | `ServerResponse` | `Mono<ServerResponse>` |
| Đọc DTO body | `request.body(MyDto.class)` | `request.bodyToMono(MyDto.class)` |
| Đọc sequence body | `request.body(new ParameterizedTypeReference<...>())` | `request.bodyToFlux(MyDto.class)` |
| Response có dữ liệu | `ServerResponse.ok().body(dto)` | `ServerResponse.ok().bodyValue(dto)` |
| Response với Publisher | Có integrations riêng nhưng không phải contract cốt lõi | `.body(flux, Item.class)` |
| Filter của functional routing | Servlet `HandlerFilterFunction` đồng bộ | WebFlux `HandlerFilterFunction` trả `Mono<ServerResponse>` |
| Web filtering toàn ứng dụng | Servlet `Filter` hoặc interceptor | Reactive `WebFilter` |
| Mục tiêu | Routing functional trên Servlet | Routing functional trên reactive HTTP runtime |

**Import chuẩn:**

```java
import org.springframework.web.reactive.function.server.HandlerFunction;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
```

**Import sai trong bài này:**

```java
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;
```

Cùng một kiểu tên `ServerResponse` nhưng bên WebFlux builder hoàn tất bằng một **Mono**. Vì thế:

```java
// WEBFLUX.FN — đúng chữ ký
HandlerFunction<ServerResponse> hello =
    request -> ServerResponse.ok().bodyValue("Hello");

// WEBMVC.FN — chữ ký của stack KHÁC
// HandlerFunction<ServerResponse> hello =
//    request -> ServerResponse.ok().body("Hello");
```

Snippet trên là phần minh họa trong một class có đúng imports reactive và là đoạn có thể sử dụng bên trong method với type thích hợp. Chỉ một dependency WebFlux là chưa đủ nếu Spring Boot cũng kéo thêm `spring-boot-starter-web`: khi hai starters hiện diện, Boot thông thường ưu tiên Servlet MVC. Kiểm tra web application type qua configuration và startup logs, không suy từ tên controller.

## 3. Vẽ đúng hai giai đoạn routing và handling

Flow căn bản:

```text
HTTP GET /api/notes/7
      │
      ▼
Reactor Netty inbound Channel
      ▼
WebFlux HttpHandler / WebHandler / WebFilter
      ▼
DispatcherHandler
      ▼
RouterFunctionMapping
      │
      └── RouterFunction.route(ServerRequest)
             │
             ├── No match: Mono.empty()
             │       → thử route/mapping tiếp, cuối cùng có thể 404
             │
             └── Match: Mono.just(HandlerFunction)
                          │
                          ▼
                  HandlerFunction.handle(ServerRequest)
                          │
                          └── Mono<ServerResponse>
                               │
                               ├── DB/WebClient publisher complete
                               ├── chọn HTTP status + headers
                               ├── ServerResponseResultHandler
                               └── ServerResponse.writeTo(response,...)
                                      │
                                      ▼
                                HTTP codecs + response body Publisher
                                      │
                                      ▼
                                  Client
```

Từ góc nhìn API chính thức, hợp đồng rút gọn:

```java
@FunctionalInterface
public interface HandlerFunction<T extends ServerResponse> {
    Mono<T> handle(ServerRequest request);
}

// Rút gọn conceptual signature của RouterFunction:
Mono<HandlerFunction<T>> route(ServerRequest request);
```

Đây là **signature-level pseudocode** để học: interface thực của Spring có generic types, annotations và các methods khác tùy phiên bản. Không copy đoạn khai báo này thành hai interface mới trùng tên với Spring.

### 3.1. “Bất đồng bộ” nghĩa gì?

`Mono<ServerResponse>` là **lời hứa theo Reactive Streams** cho việc tạo ra một response trong tương lai, không phải `Future.get()` đang chặn. Handler có thể tạo publisher ngay, còn logic đọc dữ liệu đến khi downstream subscribe mới bắt đầu:

```java
Mono<ServerResponse> response = service.find(id)
    .flatMap(note ->
        ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(note))
    .switchIfEmpty(ServerResponse.notFound().build());
```

Nếu `service.find(id)` dùng một reactive data driver, network/database wait không yêu cầu giữ thread ngồi chờ. Nhưng đoạn code **không biến JDBC blocking thành non-blocking**; phải kiểm tra dependencies và bất kỳ mapping/validation function nào chạy đồng bộ.

### 3.2. “Một response” không nghĩa “một item body”

`Mono<ServerResponse>` chỉ có tối đa **một ServerResponse descriptor**; bên trong descriptor có thể chứa:

- `String` hay `Note`: body một object/string.
- `Mono<Note>`: nguồn một entity async.
- `Flux<Note>`: nhiều entities hoặc streaming data.
- `Flux<DataBuffer>`: các chunks bytes.
- Không body: `ServerResponse.noContent().build()`.

Sơ đồ:

```text
HandlerFunction:
  Mono<ServerResponse>                  (0..1 descriptor)

ServerResponse.body:
  Publisher<T>                          (0..N onNext, theo loại publisher)

HTTP exchange:
  status/headers được gửi một lần; body có thể stream đến khi complete
```

**Không lẫn “không match router” với “response body không có item”.** Nếu route match và handler chủ động trả `ServerResponse.notFound().build()`, đó là một HTTP 404 response hợp lệ. Nếu chính handler return `Mono.empty()` thay vì tạo descriptor, HTTP result behavior không có status được quyết định rõ; tránh dựa vào đó để biểu diễn entity not found.

### 3.3. Publisher có ba tín hiệu cốt lõi

```text
Subscriber nhận onSubscribe
  → onNext(value) zero or more times
  → onComplete() HOẶC onError(error)
```

Mono tối đa một `onNext`, Flux 0..N. Null không được phát làm `onNext`. Cancellation là một tín hiệu quản lý subscription, không đồng nghĩa `onComplete`. Với HTTP client disconnect, transport có thể cancel body publisher; cleanup cần tính cả error/cancel.

## 4. ServerRequest: đọc method, URL, headers, params và body reactive

`ServerRequest` là interface bất biến ở góc nhìn handler, cung cấp các API dễ gọi hơn so với truy cập trực tiếp `ServerWebExchange`. Nó không có nghĩa request body đã được parse hoặc cache trong một Java object.

Các API thông dụng:

| Dữ liệu cần đọc | API | Kiểu/ý nghĩa |
| --- | --- | --- |
| HTTP method | `request.method()` | `HttpMethod` |
| URI | `request.uri()` | `URI` |
| Path | `request.path()` | path string |
| Path variable | `request.pathVariable("id")` | `String`, parse khi cần |
| Query param | `request.queryParam("q")` | `Optional<String>` |
| Tất cả query | `request.queryParams()` | `MultiValueMap<String,String>` |
| Headers | `request.headers()` | `ServerRequest.Headers` |
| Header đầu tiên | `request.headers().firstHeader("X-Trace-Id")` | nullable String |
| Content-Type | `request.headers().contentType()` | `Optional<MediaType>` |
| Accept | `request.headers().accept()` | `List<MediaType>` |
| Cookies | `request.cookies()` | `MultiValueMap<String,HttpCookie>` |
| Body một object | `request.bodyToMono(Command.class)` | `Mono<Command>` |
| Body nhiều items | `request.bodyToFlux(Event.class)` | `Flux<Event>` |
| Low-level HTTP | `request.exchange()` | `ServerWebExchange` |

API có thể return empty Optional khi query param không có, hoặc throw khi path variable bắt buộc không hiện diện trong mapping; không dùng chúng như đã validate input.

### 4.1. Đọc path variable và validate kiểu

Route:

```java
.GET("/api/notes/{id}", handler::get)
```

Trong handler:

```java
String raw = request.pathVariable("id");
long id;
try {
    id = Long.parseLong(raw);
} catch (NumberFormatException e) {
    return ServerResponse.badRequest()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("error", "invalid_id"));
}
```

Đây là snippet nằm trong method `Mono<ServerResponse> get(ServerRequest request)`, không chạy độc lập. Khác với annotated `@PathVariable long id`, một functional handler nhận String rồi tự convert/validate. Đặt business invariant (ID phải dương, tenant hợp lệ) ở service/handler thích hợp.

### 4.2. Query parameters

```java
String query = request.queryParam("q").orElse("").trim();
```

`?q=webflux` là query param; `/api/notes/{id}` là path variable. Với nhiều query values:

```java
List<String> tags = request.queryParams().getOrDefault(
        "tag", List.of());
```

Đây là snippet cần imports `List` và một `ServerRequest request`. Không nối raw query string vào SQL. Nếu dùng R2DBC, hãy dùng parameter binding của repository/database API, không tự ghép SQL từ request.

### 4.3. Headers

```java
String traceId = request.headers().firstHeader("X-Request-Id");

List<MediaType> accepted = request.headers().accept();

Optional<MediaType> contentType =
    request.headers().contentType();
```

Không tin một header do client đặt tên `X-Admin`/`X-Role` để phân quyền. Authentication phải dựa trên trusted credentials/context với Spring Security; business authorization còn phải kiểm tra resource ownership.

### 4.4. JSON body thành Mono<DTO>

```java
Mono<CreateNote> command =
    request.bodyToMono(CreateNote.class);
```

Điểm quan trọng:

- Đây là **Publisher**, việc decode body xảy ra theo reactive processing.
- Body rỗng có thể thành `Mono.empty()`. Với POST yêu cầu body, cần error contract 400 rõ ràng.
- JSON sai cú pháp thường dẫn tới codec decode error, không phải empty thành công.
- Media type không hỗ trợ có thể gây lỗi tương ứng; cần test status trong ứng dụng thực.
- Body stream bình thường không được đọc hai lần tùy ý; request body là tài nguyên stream theo subscription.
- Không dùng `request.bodyToMono(CreateNote.class).block()` trên WebFlux event loop.

### 4.5. Nhiều objects bằng bodyToFlux

Nếu client gửi streaming JSON/NDJSON phù hợp:

```java
Flux<Event> events = request.bodyToFlux(Event.class);
```

Từng item được emit theo codec/media type phù hợp. **Một HTTP JSON array** và **NDJSON stream** có buffering/codec/flush semantics khác nhau, dù cùng có thể decode thành Flux. Không xây API nhập một triệu items mà dùng `collectList()` vô giới hạn trước khi validate; cân nhắc limits, backpressure, batching, timeout và xử lý lỗi giữa stream.

### 4.6. ParameterizedTypeReference

Với generic type:

```java
Mono<List<CreateNote>> items =
    request.bodyToMono(new ParameterizedTypeReference<
        List<CreateNote>>() {});
```

Cần import `org.springframework.core.ParameterizedTypeReference`. Nếu dùng `List<CreateNote>` làm input, việc decode một JSON array thành toàn List có thể giữ dữ liệu lớn trong memory; đặt request body size limits và kiểm tra codec buffer limits. Nếu muốn stream dài, thiết kế input media type phù hợp và dùng Flux.

## 5. ServerResponse: status, header, cookie, body và completion

`ServerResponse` là interface theo immutable contract. Thông thường lấy builder từ các static factories rồi gọi phương thức kết thúc **trả Mono<ServerResponse>**.

| Mục tiêu | WebFlux.fn |
| --- | --- |
| 200 với object có sẵn | `ServerResponse.ok().bodyValue(note)` |
| 200 JSON từ Flux | `ServerResponse.ok().contentType(APPLICATION_JSON).body(flux, Note.class)` |
| 201 + Location | `ServerResponse.created(uri).bodyValue(note)` |
| 202 Accepted | `ServerResponse.accepted().build()` |
| 204 No Content | `ServerResponse.noContent().build()` |
| 400 Bad Request | `ServerResponse.badRequest().bodyValue(error)` |
| 404 Not Found | `ServerResponse.notFound().build()` |
| 409 Conflict | `ServerResponse.status(HttpStatus.CONFLICT).bodyValue(error)` |
| 429 Too Many Requests | `ServerResponse.status(TOO_MANY_REQUESTS).bodyValue(error)` |
| 500 Internal Error | `ServerResponse.status(INTERNAL_SERVER_ERROR).build()` |

### 5.1. bodyValue: có một giá trị sẵn

```java
return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("status", "ready"));
```

Phương thức `bodyValue` dùng với object có sẵn, như DTO/Map/String. **Không đưa một `Mono<Note>` vào bodyValue và mong Reactor tự serialize dữ liệu khi Mono complete**. Với publisher, dùng method `body(publisher, type)`.

### 5.2. body: một Publisher có thể phát nhiều values

```java
Flux<Note> notes = repository.findAll();

return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .body(notes, Note.class);
```

Đây là snippet khi đã có reactive repository phù hợp. Spring dùng message writers/codecs để serialize items. Với media type `application/json` và Flux hữu hạn, output thường là **JSON array**. **Không khẳng định** từng item flush ngay lập tức như SSE khi đang ở `application/json`.

Một Mono:

```java
Mono<Note> note = repository.findById(id);
return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .body(note, Note.class);
```

Nếu `note` empty, HTTP status ở ví dụ vẫn đã chọn 200; muốn 404 theo nghiệp vụ, hãy đợi source bằng `flatMap` trước khi tạo ServerResponse, như phần tiếp theo.

### 5.3. Trả 404 theo giá trị reactive

```java
return repository.findById(id)
    .flatMap(note ->
        ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(note))
    .switchIfEmpty(ServerResponse.notFound().build());
```

Đây là idiom WebFlux.fn rất quan trọng: **lựa chọn response phụ thuộc vào Mono có item hay empty**. Với source error, lỗi propagate, không tự biến thành 404.

### 5.4. 201 + Location khi tạo resource

```java
return service.create(command)
    .flatMap(saved ->
        ServerResponse.created(
            URI.create("/api/notes/" + saved.id()))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(saved));
```

`ServerResponse.created(uri)` set status 201 và header Location. URI tương đối dùng được trong demo; trên production cần xét host/context path/reverse proxy nếu client cần absolute Location. Không lấy Host header không tin cậy rồi lắp thẳng thành Location/open redirect.

### 5.5. 204 không có body

```java
return ServerResponse.noContent().build();
```

Khi DELETE thành công, 204 là HTTP status phù hợp nếu contract không trả body. `Mono<ServerResponse>` ở đây **phát một descriptor** có status 204, còn response body không có phần tử.

### 5.6. Header và cookie

```java
return ServerResponse.ok()
    .header("X-API-Version", "1")
    .cacheControl(CacheControl.noCache())
    .bodyValue(Map.of("ok", true));
```

Đây là snippet có `CacheControl`/`Map` imports. Set-Cookie có API `cookie(ResponseCookie)` trên builder, nhưng session/auth cookies phải có Secure, HttpOnly, SameSite, path/domain policy phù hợp. `Cache-Control: no-cache` cho phép cache lưu với revalidation, khác `no-store`.

## 6. Khi nào ServerResponse thực sự được gửi?

Một số thời điểm khác nhau:

1. Controller/Handler **assembly**: ghép Reactor pipeline, có thể chưa gọi service hay đọc body.
2. Subscription: framework bắt đầu xử lý Publisher.
3. `Mono<ServerResponse>` emit descriptor: framework biết HTTP status/headers/body publisher.
4. `ServerResponseResultHandler` ghi response qua codecs khi body Publisher emit.
5. Body complete/error/cancel; HTTP exchange kết thúc hoặc bị ngắt.

```text
Handler assembly             Mono<ServerResponse>
                                    │
Subscription                        ▼
Service I/O async             emits ServerResponse
                                    │
Response headers/status             ▼
HTTP writer subscribes        Flux<Note> body
                                    │
Output                             onNext() onNext() onComplete()
```

**Không nhầm “đã tạo Mono” với “đã thực sự gửi HTTP response”.** Nếu side effect tạo/ghi DB nằm trong một reactive Publisher, nó thường chỉ diễn ra khi subscription tương ứng được kích hoạt. Ngược lại, side effect thực hiện ngay bên ngoài factory (như `Mono.just(blockingCall())`) vẫn chạy **trước** subscription.

### 6.1. Eager vs lazy

Sai về lazy I/O:

```java
Mono<Note> note = Mono.just(
    legacyBlockingRepository.load(id)); // load chạy ngay
```

Cách trì hoãn call:

```java
Mono<Note> note =
    Mono.fromCallable(() -> legacyBlockingRepository.load(id));
```

Nhưng `fromCallable` chỉ làm việc lazy, **không làm JDBC blocking thành non-blocking**. Nếu buộc phải bridge synchronous API:

```java
Mono<Note> note =
    Mono.fromCallable(() -> legacyBlockingRepository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là các **snippets giải thích** cần variables/classes thật, không phải chương trình standalone. `boundedElastic` có giới hạn threads/queue và vẫn phải cấu hình DB pool, timeouts; dùng R2DBC/reactive driver mới có non-blocking I/O đúng nghĩa.

### 6.2. Không gọi subscribe trong HandlerFunction để “chạy nhanh hơn”

Anti-pattern:

```java
Mono<ServerResponse> create(ServerRequest request) {
    service.save(data).subscribe(); // fire-and-forget mất HTTP lifecycle
    return ServerResponse.accepted().build();
}
```

Dễ gây duplicate execution, không biết success/failure, không propagate cancellation và làm response “accepted” trước khi xác nhận sự kiện nghiệp vụ. Nếu mục tiêu thật là async job, cần durable queue/job store và HTTP 202 contract; nếu muốn hoàn tất save rồi trả 201, hãy compose bằng `flatMap` hoặc `then`, không subscribe thủ công.

## 7. HTTP status, empty và error: ba lớp dễ bị nhầm

### 7.1. Router không match

`RouterFunction.route(request)` có thể complete empty vì predicate path/method/media không match. Framework sẽ thử những router/handler mappings khác. Nếu không có handler phù hợp, HTTP có thể kết thúc 404 hoặc một status mapping-specific.

### 7.2. Handler match nhưng business source empty

`repository.findById(id)` trả `Mono.empty()` biểu thị không tìm thấy entity. Handler có trách nhiệm mapping sang HTTP 404 hoặc kết quả thay thế phù hợp. **Không** return `Mono.empty()` như một response descriptor rồi dựa vào Framework suy ra 404.

### 7.3. Handler source error

`repository.findById` trả `Mono.error(ex)` nghĩa là **thất bại**, không phải “dữ liệu không tồn tại”. Lỗi có thể đi qua WebFlux exception handling và thành 4xx/5xx theo policy. Tránh:

```java
return repository.findById(id)
    .onErrorResume(error -> Mono.empty());
```

vì có thể biến lỗi database thành HTTP 404 và che giấu outage. Với lỗi nghiệp vụ đã được phân loại (ví dụ `DuplicateKeyException`), có thể map thành 409; với lỗi không biết, giữ 5xx và log nội bộ an toàn.

### 7.4. Mô hình quyết định

| Tình huống | Reactive stream | HTTP contract đề nghị |
| --- | --- | --- |
| Không có route GET | Router Mono.empty | 404 hoặc status theo mapping infrastructure |
| GET ID tồn tại | Mono<Note> phát note | 200 + JSON |
| GET ID không tồn tại | Mono<Note> empty | Handler trả 404 |
| POST không có body | request.bodyToMono empty | Handler trả 400 |
| POST title trống | DTO hợp lệ JSON nhưng invalid business | Handler trả 400 |
| POST thành công | Service Mono<Note> phát saved note | 201 + Location |
| DELETE thành công | Service Mono<Boolean> true | 204 |
| DELETE ID không tồn tại | Service Mono<Boolean> false | 404/204 theo hợp đồng đã định |
| Service không kết nối DB | Mono.error | 5xx + monitoring; không giả 404 |
| Stream đã bắt đầu rồi lỗi | Flux phát một số items rồi error | Status có thể đã commit; protocol error/close |

## 8. RouterFunction: chọn handler một cách có thứ tự

Spring có builder `RouterFunctions.route()`:

```java
@Bean
RouterFunction<ServerResponse> routes(NoteHandler h) {
    return RouterFunctions.route()
        .GET("/api/notes/search", h::search)
        .GET("/api/notes", h::list)
        .GET("/api/notes/{id}", h::get)
        .POST("/api/notes", h::create)
        .DELETE("/api/notes/{id}", h::delete)
        .build();
}
```

WebFlux.fn **xét các routes theo thứ tự khai báo**. Đường `/api/notes/search` phải đứng trước `/api/notes/{id}`, vì path variable có thể nhận chuỗi `"search"`. Khác annotated controller mapping thường chọn most specific method.

### 8.1. RequestPredicate

Route có thể match HTTP method, path, Accept và Content-Type:

```java
return RouterFunctions.route()
    .GET("/api/notes", RequestPredicates.accept(
         MediaType.APPLICATION_JSON), handler::list)
    .POST("/api/notes", RequestPredicates.contentType(
         MediaType.APPLICATION_JSON), handler::create)
    .build();
```

Đây là snippet thay thế route definition ở trên, không phải file độc lập. `Accept` yêu cầu representation client muốn nhận; `Content-Type` diễn đạt format body client gửi. Đặt predicate quá chặt khiến request bị **không match** thay vì decode fail; status thực có thể phụ thuộc các mappings khác và WebFlux exception infrastructure. Test behavior end-to-end.

### 8.2. Nested routes

```java
return RouterFunctions.route()
    .path("/api/notes", b -> b
        .GET("/search", handler::search)
        .GET(handler::list)
        .GET("/{id}", handler::get)
        .POST(handler::create)
        .DELETE("/{id}", handler::delete))
    .build();
```

Đây là cấu hình **thay thế**, không đăng ký song song với non-nested bean cùng URL. Nested route giảm lặp prefix. Với route root path hoặc slash, cần test actual matcher; không giả định mọi dấu gạch chéo được chuẩn hóa giống nhau.

### 8.3. Composition

Có thể ghép:

```java
RouterFunction<ServerResponse> apiRoutes = ...;
RouterFunction<ServerResponse> adminRoutes = ...;

RouterFunction<ServerResponse> all =
    apiRoutes.and(adminRoutes);
```

Các snippets trên chỉ mô tả composition khi hai router variables có sẵn. Thứ tự vẫn quan trọng, đặc biệt với `/**` hoặc wildcard quá rộng. Spring Boot có thể detect nhiều RouterFunction beans, order/combine qua `RouterFunctionMapping`; nếu có cùng URL, định nghĩa ownership/order rõ và viết regression tests.

### 8.4. Một router không phải business service

Lựa chọn tốt là RouterFunction chỉ điều phối method/path/predicate; handler đọc request, validate, gọi service; service làm business/transaction; repository làm data access. Không nhét một màn hình CRUD lớn vào một lambda route vài trăm dòng rồi khó test.

## 9. HandlerFilterFunction, trước/sau xử lý và WebFilter

Functional middleware:

```java
.filter((request, next) -> {
    String blocked = request.headers()
        .firstHeader("X-Demo-Flow");
    if ("reject".equals(blocked)) {
        return ServerResponse.status(HttpStatus.TOO_MANY_REQUESTS)
            .bodyValue(Map.of("error", "demo_filtered"));
    }
    return next.handle(request);
})
```

Trong WebFlux.fn, `next.handle(request)` trả `Mono<ServerResponse>`; filter có thể short-circuit **bằng cách không gọi next**. Đây là ví dụ quan sát middleware, **không phải rate limiting hoặc security thật**. Header `X-Demo-Flow` do client tự đặt, tuyệt đối không dùng để xác thực hay phân quyền.

### 9.1. Filter là bất đồng bộ

Một handler filter có thể compose:

```java
.filter((request, next) ->
    next.handle(request)
        .doOnNext(response -> {
            // lightweight diagnostics; response descriptor có sẵn
        }))
```

Snippet cần context builder, nên không standalone. Không gọi `.block()` trong filter, không đặt network I/O sync trong callback. Khi cần xử lý exception, có thể dùng Reactor `onErrorResume` với filter policy rõ hoặc framework `WebExceptionHandler`, nhưng không nuốt toàn bộ lỗi tùy tiện.

### 9.2. before và after

Router builder có các hooks:

```java
.before(request -> ServerRequest.from(request)
    .header("X-Internal-Marker", "demo")
    .build())
.after((request, response) -> {
    // metrics/logging nhẹ, không ghi dữ liệu nhạy cảm
})
```

Các đoạn trên là code minh họa trong RouterFunction builder; scope tùy root/nested builder. Với API WebFlux version cụ thể, kiểm tra lifecycle và không mutate request object bất biến trực tiếp.

### 9.3. So sánh layers

| Công cụ | Layer | Khi nào dùng |
| --- | --- | --- |
| `HandlerFilterFunction` | Một RouterFunction hoặc route group | Pre/post hoặc short-circuit logic gắn nhóm routes |
| `WebFilter` | WebFlux WebHandler chain | Request ID, logging, security integration, CORS |
| `WebExceptionHandler` | Reactive exception handling | Error response trước commit |
| `SecurityWebFilterChain` | Reactive Spring Security | Authentication/authorization/CSRF |
| Servlet `Filter` | Servlet container/MVC | **Không phải** cơ chế trung tâm khi chạy WebFlux trên Reactor Netty |
| MVC `HandlerInterceptor` | Servlet MVC handler chain | Không dùng cho WebFlux.fn trên Netty |

Spring WebFlux functional endpoints dùng `CorsWebFilter` khi cần CORS; không dựa vào `@CrossOrigin` trên một Java HandlerFunction như với annotated controllers. CORS là browser policy, không thay authorization.

## 10. Request và response body có backpressure ra sao?

Một reactive request body thường được đọc thành `Flux<DataBuffer>` rồi decode thành Mono/Flux typed objects. Response body `Flux<Note>` được encoder đưa ra socket theo khả năng ghi/HTTP codec. **Reactive Streams có demand** giữa publisher và subscriber; transport HTTP/TCP cũng có buffers/flow control riêng.

```text
Client upload body
   ↓ network packets / Reactor Netty
   ↓ Flux<DataBuffer> request body
   ↓ HttpMessageReader decode
   ↓ request.bodyToFlux(Event.class)
   ↓ Handler/service operators
   ↓ ServerResponse.body(publisher,Event.class)
   ↓ HttpMessageWriter / encoder
   ↓ socket write readiness / client
```

### 10.1. “Publisher” không có nghĩa buffer vô hạn được phép

- `bodyToMono(List.class)` có thể cần aggregate request body lớn.
- `Flux.collectList()` phải đợi complete và giữ toàn bộ items.
- `onBackpressureBuffer()` có thể làm heap tăng không giới hạn nếu không cấu hình.
- Server/proxy/client đều có request body size/time limits cần phối hợp.
- External push producer có thể không tuân thủ demand trọn vẹn; thiết kế overflow policy và metrics.

Spring Boot có property `spring.codec.max-in-memory-size` để điều chỉnh giới hạn codec aggregation trong một số operations. Đây **không phải** một quota RAM tổng của JVM, và không phải mọi stream dài sẽ luôn được buffer toàn bộ.

### 10.2. JSON array và SSE không giống nhau

Với `Content-Type: application/json`, Flux hữu hạn thường encode thành một JSON array. Client có thể chỉ xử lý sau khi array hoàn chỉnh. Nếu cần event streaming, chọn `MediaType.TEXT_EVENT_STREAM` hoặc `application/x-ndjson` khi client/server hỗ trợ:

```java
Flux<String> events = Flux.interval(Duration.ofSeconds(1))
    .map(index -> "tick-" + index);

return ServerResponse.ok()
    .contentType(MediaType.TEXT_EVENT_STREAM)
    .body(events, String.class);
```

Đây là snippet sử dụng trong handler, cần imports `Flux`, `Duration`, `MediaType`. Demo ở mục 14 cố ý giới hạn events để không giữ kết nối mãi. Với SSE, production cần heartbeat, authorization, disconnect/cancel, replay policy, slow-consumer handling và reverse-proxy idle timeout.

### 10.3. Response đã commit và lỗi giữa stream

Khi một HTTP 200 SSE stream đã phát headers và hai events, error thứ ba không thể bảo đảm sửa status thành HTTP 500. Cần xác định protocol-level error event hoặc đóng stream/retry semantics; đừng trả JSON error object chen vào SSE stream mà không có protocol contract.

## 11. Asynchrony, schedulers, ThreadLocal và error handling

### 11.1. Mono/Flux không tự tạo thread mới

Đoạn `Mono.just("ok").map(...)` có thể chạy trên thread đang subscribe. `Flux.range` thường phát synchronously theo demand. Chính source async (WebClient/R2DBC/interval) hoặc scheduler operators thay đổi execution.

- `subscribeOn(scheduler)` ảnh hưởng quá trình subscribe/upstream.
- `publishOn(scheduler)` chuyển execution context cho downstream operators sau nó.
- `Schedulers.boundedElastic()` phù hợp hơn khi cần bridge **blocking** APIs có giới hạn.
- `Schedulers.parallel()` dành cho loại compute work phù hợp, không phải nơi để giữ blocking JDBC thread.

### 11.2. Tránh block()

Anti-pattern trong handler:

```java
Mono<ServerResponse> bad(ServerRequest request) {
    Note note = service.find(1L).block();
    return ServerResponse.ok().bodyValue(note);
}
```

Trên Reactor Netty event loop, `block()` có thể throw `IllegalStateException` hoặc gây event-loop starvation. Sửa:

```java
Mono<ServerResponse> good(ServerRequest request) {
    return service.find(1L)
        .flatMap(note -> ServerResponse.ok().bodyValue(note))
        .switchIfEmpty(ServerResponse.notFound().build());
}
```

Cả hai snippets giả định class có service phù hợp; chỉ method `good` phản ánh idiom nên dùng. Trong main/tests ở boundary imperative có thể dùng `block()` khi chủ động chờ, nhưng không trong reactive request handling.

### 11.3. Context không phải thread-local bất biến

Request có thể đổi thread. Đừng kỳ vọng `ThreadLocal`, MDC, Spring Security context dạng Servlet hay JPA transaction holder luôn có cùng giá trị. Reactor dùng `Context` per-subscriber; Spring Security reactive context propagation có infrastructure riêng. Nếu cần audit user/resource, lấy principal đáng tin cậy và truyền thông tin theo API reactive; không copy tùy tiện mutable SecurityContext qua worker threads.

### 11.4. Error như Publisher signal

Nếu body JSON sai, `bodyToMono(Command.class)` có thể phát `onError` do decode. Nếu service lỗi, `Mono.error(...)` propagate. Có thể dùng `onErrorResume(SpecificBusinessException.class, ex -> ServerResponse.status(...).bodyValue(...))` khi exception được phân loại. Lỗi chưa phân loại cần error handler chung và log có correlation, không leak stack trace cho client.

### 11.5. Timeout và cancellation

`Mono.timeout(Duration.ofSeconds(2))` là timeout của một publisher, khác TCP connect/HTTP client response timeout, pool acquisition timeout và business deadline. Khi timeout/cancel propagate, remote service có thể đã nhận POST, side effects có thể vẫn tiếp tục; dùng idempotency/transaction/retry policy. `doFinally` chạy với complete/error/cancel thích hợp để cleanup, nhưng tránh blocking trong callback.

## 12. Ứng dụng thực tế nào phù hợp WebFlux.fn?

| Bài toán | Có phù hợp không? | Lý do |
| --- | --- | --- |
| REST CRUD với reactive repository | Phù hợp | Compose Mono/Flux theo contract HTTP |
| API proxy bằng WebClient non-blocking | Phù hợp | Không cần giữ worker chờ remote network |
| Event streaming SSE | Phù hợp | Body Publisher nhiều items, cancel/backpressure |
| API toàn bộ JPA/JDBC blocking | Cân nhắc | Reactive wrapper không tự non-blocking |
| HTML SSR với templates | Có thể nhưng cần integration | WebFlux view resolver/Rendering hoặc annotated controllers |
| Legacy Servlet Filter/JSP stack lớn | Có thể MVC thuận lợi hơn | Servlet integration không map 1:1 sang Netty |
| Cần routing khai báo tập trung/composable | Phù hợp | RouterFunction builder dễ nhóm |
| Một vài annotated controllers đơn giản | Không bắt buộc chuyển | WebFlux annotated API cũng được hỗ trợ |
| Long-running background job nhiều phút | Dùng durable job store hơn giữ HTTP | 202+job ID, poll/status/events |

### 12.1. Khi nào nên dùng WebFlux annotated controllers?

Nếu đội đã quen DTO validation qua `@Valid`, `@RequestBody`, handler advice và OpenAPI generators, annotated WebFlux có thể tự nhiên hơn. WebFlux.fn không phải cách duy nhất để hưởng non-blocking I/O. Chọn style theo tính nhất quán và tooling; lựa chọn **WebFlux reactive stack** là quyết định khác với lựa chọn **functional hay annotation routing**.

### 12.2. Validation thủ công trong HandlerFunction

Với functional route, bạn thường nhận DTO qua `bodyToMono` và cần validate cụ thể. Với Jakarta Bean Validation, có thể inject `jakarta.validation.Validator`, gọi `validator.validate(command)` rồi mapping violations. Không mặc nhiên giả định đặt `@Valid` trong record rồi `bodyToMono` tự động trigger method argument validation y hệt annotated `@RequestBody @Valid`.

Với upload/form, APIs của `ServerRequest.formData()`/`multipartData()` có reactive semantics; cần cẩn thận file buffers, kích thước và lifecycle của `Part`.

## 13. Hệ thống gỡ lỗi theo tầng

| Hiện tượng | Nguyên nhân hay gặp | Hướng kiểm tra |
| --- | --- | --- |
| Method trả `ServerResponse` nhưng compiler đòi `Mono<ServerResponse>` | Import WebFlux.fn nhưng dùng signature WebMvc.fn | Return builder Publisher |
| Import `org.springframework.web.servlet.function` sai | Nhầm stack | Chuyển sang `web.reactive.function.server` |
| GET /api/notes/search báo invalid_id | Route `/{id}` đứng trước `/search` | Đặt route static trước variable |
| GET entity không tồn tại lại 200 | Chọn response trước khi `Mono.empty` resolve | Dùng flatMap + switchIfEmpty |
| JSON request empty dẫn tới no response | Không handle Mono.empty | Explicit badRequest |
| `bodyValue(flux)` không hoạt động như kỳ vọng | Nhầm object value với publisher | Dùng `body(flux, Note.class)` |
| Spring Boot chạy DispatcherServlet | Vô tình thêm starter-web | Chỉ starter-webflux cho reactive app |
| Handler không được tìm thấy | RouterFunction không phải Spring bean | Đăng ký @Bean/router config |
| Không serialize được record | Jackson/codec dependency hoặc incompatible DTO | Kiểm tra starter-webflux, model, Content-Type |
| Client gửi `text/plain` tới JSON body route | Media type không phù hợp | Content-Type và codec handlers |
| `onErrorResume` che lỗi DB thành 404 | Nuốt errors | Chỉ convert chính xác business error |
| Infinite Flux với collectList không trả | Chờ completion không đến | Streaming/lấy hữu hạn |
| Callback gọi RestTemplate/JDBC đồng bộ | Event loop block | Dùng WebClient/R2DBC hoặc offload hợp lý |
| Browser CORS error nhưng curl OK | CORS là browser policy | CorsWebFilter, OPTIONS, Security |
| filter không áp route như kỳ vọng | Nested filter scope khác root | Kiểm tra builder composition |
| WebClient timeout dù inbound còn rảnh | Outbound connection pool/pending acquire đầy | Pool metrics, remote latency |
| Test dùng MockMvc cho Netty WebFlux | Nhầm testing stack | Dùng WebTestClient |
| 404 từ router nhưng annotated handler vẫn trả 200 | Mappings có thứ tự khác | Kiểm tra RouterFunctionMapping/DispatcherHandler |
| Header đã được gửi rồi handler gặp lỗi | Response đã committed | Streaming protocol/error contract |
| Số item response không như tưởng | Flux JSON vs SSE writer | Media type, codec, backpressure |

## 14. Demo chạy được: Spring Boot 3 + Java 17 + WebFlux.fn

Mục đích của dự án: **chứng minh ngay ở code và HTTP response rằng hợp đồng WebFlux.fn là bất đồng bộ** nhưng service/middleware vẫn kiểm soát HTTP semantics đúng.

Endpoints:

- `GET /api/notes` → `Flux<Note>`, JSON array.
- `GET /api/notes/search?q=Spring` → Flux lọc từ in-memory service.
- `GET /api/notes/{id}` → Mono<Note> hoặc `ServerResponse.notFound()`.
- `POST /api/notes` → JSON `CreateNote`, 400 khi invalid, 201+Location khi hợp lệ.
- `DELETE /api/notes/{id}` → 204 khi xóa, 404 khi không tồn tại.
- `GET /api/notes/events` → ba SSE events từ Flux timer, chứng minh body Publisher nhiều values.
- `GET /api/ping` → dùng `Mono.defer` minh họa response builder Publisher.
- `GET /annotated/ping` → một annotated WebFlux controller cạnh functional router.
- Functional filter demo `X-Demo-Flow: reject` → 429, không phải security thật.

In-memory data reset khi restart; dùng `ConcurrentHashMap`, `AtomicLong` vì nhiều requests có thể xử lý song song. Đây là sample tự học, **không cung cấp authentication/rate limit production**.

### 14.1. Cấu trúc file

```text
webflux-fn-contract/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── WebFluxFnApplication.java
    │   ├── Note.java
    │   ├── CreateNote.java
    │   ├── NoteService.java
    │   ├── NoteHandler.java
    │   ├── NoteRoutes.java
    │   └── AnnotatedPing.java
    └── test/java/example/
        ├── NoteApiTest.java
        └── NoteServiceTest.java
```

### 14.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>webflux-fn-contract</artifactId>
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
```

Không thêm `spring-boot-starter-web` để tránh Boot chuyển sang Servlet MVC mặc định. `reactor-test` mang `StepVerifier`; `starter-test` mang JUnit 5 và WebTestClient testing hỗ trợ.

### 14.3. WebFluxFnApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxFnApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxFnApplication.class, args);
    }
}
```

### 14.4. Note.java và CreateNote.java

File `Note.java`:

```java
package example;

public record Note(long id, String title) {}
```

File `CreateNote.java`:

```java
package example;

public record CreateNote(String title) {}
```

Hai record là DTO contract riêng. Không lấy owner/role từ client-supplied body rồi tin đó là authorization context. Thực tế thêm validation schema, whitespace constraints và giới hạn title.

### 14.5. NoteService.java

```java
package example;

import java.util.Comparator;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class NoteService {

    private final Map<Long, Note> notes = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(2);

    public NoteService() {
        notes.put(1L, new Note(1L, "Spring WebFlux"));
    }

    public Flux<Note> list(String query) {
        String wanted = query.toLowerCase(Locale.ROOT);
        return Flux.defer(() ->
            Flux.fromIterable(notes.values())
                .filter(note -> note.title()
                    .toLowerCase(Locale.ROOT).contains(wanted))
                .sort(Comparator.comparingLong(Note::id))
        );
    }

    public Mono<Note> find(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(notes.get(id)));
    }

    public Mono<Note> create(CreateNote command) {
        return Mono.fromSupplier(() -> {
            long id = nextId.getAndIncrement();
            Note note = new Note(id, command.title().trim());
            notes.put(id, note);
            return note;
        });
    }

    public Mono<Boolean> delete(long id) {
        return Mono.fromSupplier(() -> notes.remove(id) != null);
    }
}
```

- `Flux.defer`/`Mono.defer` khiến mỗi subscription quan sát snapshot/giá trị tại thời điểm subscribe; code không tự query trước khi subscribe.
- `ConcurrentHashMap` bảo vệ operations map cơ bản và `AtomicLong` cấp ID không trùng trong **một JVM instance**, không phải distributed persistence/transaction.
- `sort(...)` cần buffer toàn sequence. In-memory 1–vài notes không sao; với dữ liệu lớn phải sort/paginate **ở database query**, không đem triệu records về rồi sort trong Flux.
- `create` không được subscribe hai lần nếu muốn tránh tạo hai notes. HTTP framework sẽ quản lý subscription bình thường; service API production cần idempotency key cho POST retried.
- Đây là **cold reactive wrapper trên in-memory operations nhỏ**, không phải bằng chứng có non-blocking DB I/O. Thay bằng R2DBC/reactive repository khi làm hệ thống thật.

### 14.6. NoteHandler.java

```java
package example;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class NoteHandler {

    private final NoteService service;

    public NoteHandler(NoteService service) {
        this.service = service;
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        String q = request.queryParam("q").orElse("").trim();

        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(service.list(q), Note.class);
    }

    public Mono<ServerResponse> search(ServerRequest request) {
        return list(request);
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        Long id = parseId(request);
        if (id == null) {
            return badId();
        }

        return service.find(id)
            .flatMap(note ->
                ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(note))
            .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateNote.class)
            .flatMap(command -> {
                if (command.title() == null ||
                        command.title().isBlank()) {
                    return ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of(
                            "error", "title_required"));
                }

                if (command.title().trim().length() > 120) {
                    return ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of(
                            "error", "title_too_long"));
                }

                return service.create(command)
                    .flatMap(saved -> ServerResponse.created(
                                URI.create("/api/notes/" + saved.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(saved));
            })
            .switchIfEmpty(ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("error", "body_required")));
    }

    public Mono<ServerResponse> delete(ServerRequest request) {
        Long id = parseId(request);
        if (id == null) {
            return badId();
        }

        return service.delete(id)
            .flatMap(existed -> existed
                ? ServerResponse.noContent().build()
                : ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> events(ServerRequest request) {
        Flux<String> source = Flux.interval(Duration.ofMillis(20))
            .take(3)
            .map(index -> "tick-" + index);

        return ServerResponse.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(source, String.class);
    }

    public Mono<ServerResponse> ping(ServerRequest request) {
        return Mono.defer(() ->
            ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("status", "ready")));
    }

    private Long parseId(ServerRequest request) {
        try {
            long id = Long.parseLong(request.pathVariable("id"));
            return id > 0 ? id : null;
        } catch (NumberFormatException ex) {
            return null;
        }
    }

    private Mono<ServerResponse> badId() {
        return ServerResponse.badRequest()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("error", "invalid_id"));
    }
}
```

#### Vì sao handler này thực sự reactive?

Chú ý return type của **mọi** method là `Mono<ServerResponse>`. Handler không trả trực tiếp `ServerResponse`, không gọi `block()` hay `subscribe()`.

- `list()` tạo response descriptor có body `Flux<Note>`; framework subscribe body khi ghi.
- `get()` đợi `service.find(id)`; nếu entity empty mới tạo response 404. Không có phản hồi 200 sai khi dữ liệu không tồn tại.
- `create()` dùng `bodyToMono(CreateNote.class)`, validate rồi `flatMap` sang service create. Khi body empty, `switchIfEmpty` trả 400.
- `delete()` biến Mono<Boolean> thành 204/404 theo quy tắc business.
- `events()` trả response descriptor một lần, body stream thêm ba values từ Flux.
- `ping()` dùng `Mono.defer` để minh họa việc tạo descriptor lúc subscription.

**Chú ý HTTP error:** body JSON sai cú pháp do codec decode có thể gây HTTP 400 qua WebFlux exception handling, nhưng ví dụ chỉ custom `error: body_required/title_required/title_too_long` cho những trường hợp do handler kiểm soát. Đừng hardcode rằng mọi malformed JSON đều có chính xác cùng JSON error schema.

### 14.7. NoteRoutes.java

```java
package example;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class NoteRoutes {

    @Bean
    RouterFunction<ServerResponse> noteRouter(NoteHandler handler) {
        return RouterFunctions.route()
            .GET("/api/notes/search", handler::search)
            .GET("/api/notes/events", handler::events)
            .GET("/api/notes", handler::list)
            .GET("/api/notes/{id}", handler::get)
            .POST("/api/notes", handler::create)
            .DELETE("/api/notes/{id}", handler::delete)
            .GET("/api/ping", handler::ping)
            .filter((request, next) -> {
                if ("reject".equals(request.headers()
                        .firstHeader("X-Demo-Flow"))) {
                    return ServerResponse.status(
                            HttpStatus.TOO_MANY_REQUESTS)
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of(
                            "error", "demo_filtered"));
                }
                return next.handle(request);
            })
            .build();
    }
}
```

Đây là router một bean, tránh concurrency/order không rõ giữa nhiều beans. Đặt `/api/notes/search` và `/api/notes/events` trước `/api/notes/{id}`. Functional filter root builder áp dụng mọi routes vừa build (gồm `/api/ping`), nhưng không áp cho annotated controller riêng ở phần sau.

`ServerResponse.status(429)` có thể được trả ngay từ filter; **không có authorization/security thật**. Nếu app công khai, đừng dùng header demo này làm quyết định rate limit, vì client có thể tự gửi hoặc bỏ header.

### 14.8. AnnotatedPing.java

```java
package example;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class AnnotatedPing {

    @GetMapping("/annotated/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("style", "annotated-webflux"));
    }
}
```

Spring Boot WebFlux có thể vận hành `RouterFunction` và `@RestController` song song trên cùng `DispatcherHandler`. Không khai báo overlap giữa hai styles trừ khi có chính sách handler mapping order rõ. Functional route nhận `Mono<ServerResponse>`; annotated REST route nhận `Mono<DTO>` và để HTTP writer xử lý.

### 14.9. Chạy chương trình

Trong thư mục chứa `pom.xml`, với JDK 17+, Maven và khả năng tải dependencies:

```bash
mvn test
mvn spring-boot:run
```

Kỳ vọng Netty server chạy trên port 8080 khi chưa đổi cấu hình. Đó là **kỳ vọng cấu hình mặc định**, không phải lời khẳng định bài kiểm thử đã chạy trong môi trường hiện tại.

Đọc note seed:

```bash
curl -i http://localhost:8080/api/notes/1
```

HTTP 200 và body JSON cấu trúc:

```json
{"id":1,"title":"Spring WebFlux"}
```

Đọc không tồn tại:

```bash
curl -i http://localhost:8080/api/notes/999
```

HTTP 404; body có thể do framework tạo hoặc empty, không assert raw error format.

Danh sách:

```bash
curl -i http://localhost:8080/api/notes
```

HTTP 200:

```json
[{"id":1,"title":"Spring WebFlux"}]
```

Route static search:

```bash
curl -i "http://localhost:8080/api/notes/search?q=Spring"
```

Kỳ vọng HTTP 200 với một note. Nếu đổi thứ tự router cho `/{id}` lên trước `/search`, chuỗi `search` có thể bị parse sai dẫn tới 400, vì vậy thứ tự là một phần của behavior.

Create:

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H "Content-Type: application/json" \
  -d '{"title":"Reactor API"}'
```

HTTP 201, `Location: /api/notes/2` trong app mới khởi động, body:

```json
{"id":2,"title":"Reactor API"}
```

Nếu concurrent requests đã tạo notes, ID không còn nhất thiết là 2. Client thực cần đọc Location header.

Request body rỗng hoặc title blank:

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H "Content-Type: application/json" \
  -d '{}'

curl -i -X POST http://localhost:8080/api/notes \
  -H "Content-Type: application/json" \
  -d '{"title":"   "}'
```

Cả hai đều có thể đến handler với `CreateNote.title() == null` hoặc blank, trả HTTP 400 với `error: title_required`. Nếu gửi **hoàn toàn không có request body**, `bodyToMono` empty và handler trả `body_required`.

Xóa ID mới:

```bash
curl -i -X DELETE http://localhost:8080/api/notes/2
```

Nếu ID 2 tồn tại, kết quả là 204 không body. Gọi DELETE lại thì 404 theo policy demo. Trong một API khác, DELETE idempotent có thể trả 204 cho cả hai; **idempotent semantics không yêu cầu status phải giống nhau** khi lặp request, mà yêu cầu intended side effect ổn định.

Test filter:

```bash
curl -i -H "X-Demo-Flow: reject" \
  http://localhost:8080/api/notes
```

HTTP 429:

```json
{"error":"demo_filtered"}
```

SSE:

```bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8080/api/notes/events
```

Response Content-Type `text/event-stream`, body có dữ liệu tương ứng các ticks 0,1,2. Event formatting/chunk boundaries do codecs và transport quyết định; không assert chunk bytes như một contract API nếu không thiết kế event schema rõ.

Annotated endpoint:

```bash
curl -i http://localhost:8080/annotated/ping
```

Body JSON:

```json
{"style":"annotated-webflux"}
```

Các lệnh curl dùng syntax shell POSIX. Trên PowerShell dùng `curl.exe` và điều chỉnh nối dòng.

## 15. Test WebTestClient: kiểm chứng HTTP contract cuối cùng

Dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `@AutoConfigureWebTestClient` để kiểm thử embedded WebFlux server, codecs, RouterFunction bean và handler thực. Không dùng MockMvc để suy kết luận về Reactor Netty trong demo này.

File `src/test/java/example/NoteApiTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NoteApiTest {

    @Autowired
    WebTestClient client;

    @Test
    void seededItemIsReadable() {
        client.get().uri("/api/notes/1")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$.id").isEqualTo(1)
                .jsonPath("$.title").isEqualTo("Spring WebFlux");
    }

    @Test
    void missingEntityIsExplicit404() {
        client.get().uri("/api/notes/999999")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void invalidPathVariableIs400() {
        client.get().uri("/api/notes/not-number")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
                .jsonPath("$.error").isEqualTo("invalid_id");
    }

    @Test
    void listEmitsJsonArray() {
        client.get().uri("/api/notes")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$[0].id").isEqualTo(1);
    }

    @Test
    void staticSearchRoutePrecedesIdRoute() {
        client.get().uri("/api/notes/search?q=Spring")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$[0].title").isEqualTo("Spring WebFlux");
    }

    @Test
    void noSearchResultsIsAnEmptyArray() {
        client.get().uri("/api/notes/search?q=NoMatchAtAll")
            .exchange()
            .expectStatus().isOk()
            .expectBody().json("[]");
    }

    @Test
    void blankTitleIs400() {
        client.post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"   \"}")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
                .jsonPath("$.error").isEqualTo("title_required");
    }

    @Test
    void createReturns201LocationAndGetWorks() {
        String location = client.post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"New note\"}")
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
                .jsonPath("$.title").isEqualTo("New note")
                .returnResult()
                .getResponseHeaders()
                .getFirst(HttpHeaders.LOCATION);

        assertNotNull(location);
        assertTrue(location.startsWith("/api/notes/"));

        client.get().uri(location)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.title").isEqualTo("New note");
    }

    @Test
    void deletingCreatedItemReturns204Then404() {
        String location = client.post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Delete me\"}")
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
                .returnResult()
                .getResponseHeaders()
                .getFirst(HttpHeaders.LOCATION);

        assertNotNull(location);

        client.delete().uri(location)
            .exchange()
            .expectStatus().isNoContent()
            .expectBody().isEmpty();

        client.get().uri(location)
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void functionalFilterCanShortCircuit() {
        client.get().uri("/api/notes")
            .header("X-Demo-Flow", "reject")
            .exchange()
            .expectStatus().isEqualTo(429)
            .expectBody()
                .jsonPath("$.error").isEqualTo("demo_filtered");
    }

    @Test
    void pingReturnsReactiveResponseBuilder() {
        client.get().uri("/api/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.status").isEqualTo("ready");
    }

    @Test
    void annotatedHandlerCanCoexistWithFunctionalRouter() {
        client.get().uri("/annotated/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.style").isEqualTo("annotated-webflux");
    }

    @Test
    void eventStreamUsesSseMediaType() {
        client.get().uri("/api/notes/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_EVENT_STREAM);
    }
}
```

**13 HTTP tests** trong class trên kiểm tra đúng route, status và JSON fields. Test create lấy Location từ response, không hardcode ID 2 để tránh phụ thuộc thứ tự tests. Nhưng controller state ở @SpringBootTest context dùng chung nên một production suite lớn nên có cleanup/isolation thêm, hoặc tạo app context riêng. Không assert số thread/event-loop vì đó là detail runtime.

### 15.1. Test RouterFunction riêng mà không mở server

Spring WebFlux cho phép `WebTestClient.bindToRouterFunction(router).build()` để test router/handler mà không start real network listener.

Snippet:

```java
WebTestClient client =
    WebTestClient.bindToRouterFunction(noteRouter).build();

client.get().uri("/api/ping")
    .exchange()
    .expectStatus().isOk();
```

Cần RouterFunction bean `noteRouter` đã được tạo/truyền vào method test và imports phù hợp. Cách này hữu ích cho unit/integration mức routing; test embedded Netty ở trên bổ sung validation của server integration/auto-configuration.

### 15.2. Test SSE sâu hơn

Để verify **ba events thực**, không chỉ media type, có thể dùng:

```java
FluxExchangeResult<String> result =
    client.get().uri("/api/notes/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
    .expectNext("tick-0", "tick-1", "tick-2")
    .verifyComplete();
```

Đây là snippet cần imports `FluxExchangeResult`, `reactor.test.StepVerifier`, `MediaType`, và biến `client` có sẵn. Behavior decode SSE dưới dạng String có thể phụ thuộc codec/accept setup; nếu có sự khác biệt, ưu tiên return body dưới kiểu `ServerSentEvent<String>` và assert `event.data()` theo negotiated SSE representation. Dù là test stream, tránh chạy vô hạn và đợi không có timeout.

## 16. StepVerifier: test đúng reactive completion, empty và side effect

HTTP tests đảm bảo ứng dụng trả status/body; Reactor tests kiểm tra Publisher signals, cũng hữu ích để chứng minh không có hidden blocking `get()` trong code.

File `src/test/java/example/NoteServiceTest.java`:

```java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class NoteServiceTest {

    private NoteService service;

    @BeforeEach
    void setup() {
        service = new NoteService();
    }

    @Test
    void findExistsEmitsOneValueThenCompletes() {
        StepVerifier.create(service.find(1L))
            .expectNext(new Note(1L, "Spring WebFlux"))
            .verifyComplete();
    }

    @Test
    void findMissingCompletesEmptyNotError() {
        StepVerifier.create(service.find(777L))
            .verifyComplete();
    }

    @Test
    void listEmitsOneSeedItem() {
        StepVerifier.create(service.list("spring"))
            .expectNext(new Note(1L, "Spring WebFlux"))
            .verifyComplete();
    }

    @Test
    void createIsLazyAndDoesNotRunBeforeSubscribe() {
        var publisher = service.create(new CreateNote("Lazy"));
        StepVerifier.create(service.list("lazy"))
            .verifyComplete();

        StepVerifier.create(publisher)
            .assertNext(note -> {
                assertEquals(2L, note.id());
                assertEquals("Lazy", note.title());
            })
            .verifyComplete();
    }

    @Test
    void deleteIsFirstTrueThenFalse() {
        StepVerifier.create(service.delete(1L))
            .expectNext(true)
            .verifyComplete();

        StepVerifier.create(service.delete(1L))
            .expectNext(false)
            .verifyComplete();
    }
}
```

**5 Reactor StepVerifier tests** xác nhận empty không phải error, việc tạo note lazy và kết quả delete tường minh. Điều đó không chứng minh throughput cao/low latency trên Netty; cần load test, profiling và fake/real reactive I/O drivers để đo năng lực thực.

## 17. Hướng phát triển lên service production

Một API thật cần thêm một số lớp, không copy demo in-memory nguyên xi:

### 17.1. Persistence

Dùng `ReactiveCrudRepository<NoteEntity,Long>`/R2DBC khi muốn reactive relational database. Với tài nguyên phân trang, viết query có LIMIT/cursor thay vì `findAll().collectList()` trên toàn bảng. Với transaction, dùng reactive transaction integration và kiểm tra context propagation.

### 17.2. Security và ownership

Spring Security WebFlux cấu hình `SecurityWebFilterChain`. Route-level `HandlerFilterFunction` có thể bổ sung checks domain-specific nhưng **không** thay authentication, CSRF, authorization theo principal và resource/tenant. Trên API POST/DELETE, client không nên được cấp quyền qua custom X-Role header.

### 17.3. HTTP preconditions và caching

Nếu cần ETag/Last-Modified để revalidate GET, có thể trả appropriate headers/conditional response dựa trên stable resource version. Đừng hash toàn body đắt đỏ rồi cho rằng DB computation đã được tránh; early validator từ metadata mới cho phép short circuit. Với user-specific responses, xem `private/no-store` và Vary/Accept-Encoding.

### 17.4. Observability

Ghi các metrics: route match/status/error count, inbound active requests, event loop lag, outbound WebClient pool active/pending, downstream latency, Reactor cancellation, buffer pressure, retry/backoff, p95/p99. Với tracing, dùng Reactor Context và Spring observability integration thay vì tự tin mọi ThreadLocal MDC được truyền tự động.

### 17.5. Tests ngoài WebTestClient

Thêm tests cho request JSON malformed, Content-Type mismatch, missing body, unknown/delete race, SSE complete/error/cancel, CORS preflight, CSRF, auth/role/tenant and large-body limits. Load test với proxy/TLS/HTTP2 nếu deploy có những layers ấy. Không chỉ assert 200/201 mà còn thử error path, timeout và idempotency key.

## 18. Lỗi phổ biến: từ signature đến production

| Hiểu nhầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “WebFlux.fn HandlerFunction trả ServerResponse” | Nó trả Mono<ServerResponse> | Đúng reactive signature |
| “WebFlux RouterFunction trả Optional” | Mono<HandlerFunction> | Phân biệt WebMvc.fn |
| “Mono<ServerResponse> tức response body một item” | Descriptor có body Publisher 0..N | Tách response và body lifecycle |
| “Router Mono.empty tương đương entity not found” | Hai giai đoạn khác nhau | Route match và service lookup tách |
| “bodyToMono trả ngay DTO” | Nó trả Publisher | flatMap/map |
| “bodyToFlux luôn có nhiều items” | Flux có thể empty hoặc chỉ một item | 0..N |
| “ServerResponse.ok().bodyValue(flux) tự subscribe Flux” | bodyValue dành cho value object | Dùng body(flux, Class) |
| “Mono.empty của service tự cho 404” | Status chưa được quyết định | switchIfEmpty(notFound) |
| “Mono.error cũng là không có dữ liệu” | Error khác empty | Propagate/map error đúng |
| “Thêm @RestController cho HandlerFunction” | RouterFunction bean mới là mapping | Đăng ký router và handler |
| “Chỉ cần starter-webflux thì chắc chắn reactive” | starter-web có thể khiến Boot chọn MVC | Kiểm tra dependencies/context |
| “Route search có thể đặt sau {id}” | First match wins | Static route trước |
| “Request body đọc đi đọc lại được” | Stream không auto-replay | Decode một lần rồi reuse DTO |
| “Mono.just(blocking()) là lazy” | Argument eager | defer/fromCallable và scheduler |
| “Mono.fromCallable làm JDBC non-blocking” | Chỉ trì hoãn execution | Offload hoặc dùng driver reactive |
| “Gọi block() trong Netty là bình thường” | Block event loop/throw exception | Compose reactive operations |
| “Gọi subscribe() trong handler để save nhanh” | Lifecycle/sai error/retry handling | Return/combine Publisher |
| “Stream có backpressure là không bao giờ OOM” | Hot sources/buffers vẫn có giới hạn | Bounded resource policy |
| “Flux JSON array flush theo mỗi onNext” | Codec/media type buffering khác | SSE/NDJSON khi cần |
| “HTTP 200 SSE sau commit đổi thành 500 tùy ý” | Headers đã commit | Event-level error/close |
| “Filter đọc X-Role là security” | Header client giả được | SecurityWebFilterChain/authz |
| “Có ít event loop threads thì response miễn phí” | CPU/memory/buffer/conn vẫn tốn | Profile và cap concurrency |
| “CORS tương đương authorization” | CORS là browser policy | AuthN/AuthZ riêng |
| “Reactor Context là HttpSession” | Khác scope/lifecycle | Context/principal đúng |
| “Retry POST tự động an toàn” | Có thể duplicate side effects | Idempotency key và dedupe |
| “WebTestClient pass chứng minh Netty nhanh” | Chỉ xác minh correctness | Load/performance tests |
| “R2DBC mọi query đều phát từng row không buffer” | Driver/query/operator có thể aggregate | Đo data flow, pagination |

## 19. Checklist thiết kế WebFlux.fn

Trước khi hoàn thiện một API:

1. [ ] Import đúng `org.springframework.web.reactive.function.server`.
2. [ ] Mọi HandlerFunction trả `Mono<ServerResponse>`; không block và không subscribe thủ công.
3. [ ] RouterFunction bean được Boot/WebFlux detect; không trùng route annotated.
4. [ ] Các routes cụ thể trước `/{id}` và wildcard.
5. [ ] RequestPredicate phân biệt method/path/Accept/Content-Type rõ.
6. [ ] Path/query/header parsing và input validation có error contract.
7. [ ] Body decoded bằng `bodyToMono`/`bodyToFlux` một lần phù hợp.
8. [ ] Chọn `bodyValue` cho một value, `body(publisher,type)` cho reactive body.
9. [ ] Status 404/400/201+Location/204 được tạo **tường minh**.
10. [ ] Không nuốt lỗi DB/network thành `Mono.empty()`.
11. [ ] Service reactive end-to-end hoặc blocking bridge được offload/giới hạn.
12. [ ] Streaming media type, client cancellation và backpressure được thiết kế.
13. [ ] Filters functional/WebFilter/SecurityWebFilterChain đặt đúng layer.
14. [ ] CSRF/CORS/authentication/authorization theo trust boundary.
15. [ ] Connections, buffers, concurrency, timeouts, retries và event-loop latency có metric.
16. [ ] Tests kiểm tra success, invalid, missing, empty, error và stream.
17. [ ] POST retries và DELETE semantics/idempotency có chính sách.
18. [ ] Domain service tách khỏi RouterFunctions và DTO tách khỏi persistence entities.
19. [ ] Actual Spring Boot application type là reactive chứ không vô tình MVC.
20. [ ] Kết quả performance được đo chứ không suy từ việc class return Mono.

## 20. Câu hỏi ôn tập có đáp án

**1.** `HandlerFunction<ServerResponse>` trong WebFlux.fn trả kiểu gì?  
**Đáp án:** `Mono<ServerResponse>`.

**2.** `RouterFunction<ServerResponse>.route` có kiểu kết quả gì khi match?  
**Đáp án:** `Mono<HandlerFunction<ServerResponse>>` phát một handler.

**3.** Không match một route được biểu diễn ra sao?  
**Đáp án:** Routing publisher complete empty để framework thử mapping khác.

**4.** Package ServerRequest WebFlux.fn?  
**Đáp án:** `org.springframework.web.reactive.function.server.ServerRequest`.

**5.** Package ServerRequest WebMvc.fn?  
**Đáp án:** `org.springframework.web.servlet.function.ServerRequest`.

**6.** Đọc JSON body thành DTO trong WebFlux.fn dùng gì?  
**Đáp án:** `request.bodyToMono(Dto.class)`.

**7.** Khi body chứa nhiều records, dùng gì?  
**Đáp án:** `request.bodyToFlux(Record.class)` nếu codec/media type phù hợp.

**8.** Tạo response có một DTO sẵn dùng gì?  
**Đáp án:** `ServerResponse.ok().bodyValue(dto)`.

**9.** Tạo response body Flux dùng gì?  
**Đáp án:** `ServerResponse.ok().body(flux, Item.class)`.

**10.** `Mono<ServerResponse>` nghĩa response chỉ có một body record không?  
**Đáp án:** Không; ServerResponse descriptor có thể bọc Flux 0..N.

**11.** Service `Mono.empty()` sau khi route match có tự là HTTP 404 không?  
**Đáp án:** Không, handler phải chọn status bằng switchIfEmpty.

**12.** Response cho create thường có status và header nào?  
**Đáp án:** 201 Created và Location.

**13.** DELETE thành công không trả body nên chọn gì?  
**Đáp án:** `ServerResponse.noContent().build()` cho 204 theo API policy.

**14.** Tại sao `/search` phải trước `/{id}`?  
**Đáp án:** Routes WebFlux.fn được thử theo thứ tự, first-match wins.

**15.** `HandlerFilterFunction` có thể không gọi next không?  
**Đáp án:** Có, nó có thể short-circuit một request.

**16.** `HandlerFilterFunction` có thay Spring Security không?  
**Đáp án:** Không, authorization và auth phải dùng trust context.

**17.** `Mono.just(legacyJDBC.query())` là non-blocking không?  
**Đáp án:** Không, JDBC query đã chạy trước khi Mono được tạo.

**18.** `Mono.fromCallable` tự làm blocking call thành non-blocking không?  
**Đáp án:** Không, cần scheduler phù hợp hoặc reactive I/O driver.

**19.** Gọi `block()` trên Reactor Netty event loop có vấn đề gì?  
**Đáp án:** Có thể block loop hoặc bị Reactor từ chối.

**20.** Một response 200 SSE đã gửi data có luôn sửa status thành 500 sau lỗi không?  
**Đáp án:** Không khi headers đã committed.

**21.** CORS có thay thế kiểm tra owner/tenant không?  
**Đáp án:** Không; CORS là browser access policy.

**22.** WebTestClient dùng cho gì?  
**Đáp án:** Kiểm thử routing, HTTP status, headers, body và integration của reactive stack.

**23.** `StepVerifier` xác minh điều gì khác WebTestClient?  
**Đáp án:** onNext/onComplete/onError/empty trên Publisher.

**24.** Nếu cần sự kiện liên tục từ Flux, dùng media type nào?  
**Đáp án:** Thường dùng text/event-stream hoặc NDJSON tùy client/protocol.

**25.** Reactive Routing có thay đổi bản chất CPU-heavy task không?  
**Đáp án:** Không, CPU-bound vẫn cần CPU và capacity plan.

## 21. Tài liệu chính thức

- [Spring Framework 6.2 — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): bất đồng bộ của `RouterFunction` và `HandlerFunction`, ServerRequest/ServerResponse, handlers, predicates, routing, filters, resources.
- [Spring Framework 6.2 — WebMvc Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): so sánh chữ ký Servlet `Optional`/`ServerResponse` và reactive `Mono`.
- [Spring Framework 6.2 — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): RouterFunctionMapping, HandlerFunctionAdapter và ServerResponseResultHandler.
- [Spring Framework 6.2 — WebFlux WebHandler API](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/web-handler-api.html): HTTP server chain và WebFilter.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): API HTTP tests cho WebFlux.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): WebFlux auto-configuration và runtime.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono/Flux, lazy subscription, schedulers, backpressure, error/cancel.
- [Reactive Streams specification](https://www.reactive-streams.org/): Publisher/Subscriber/Subscription và demand.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status codes, HTTP request/response, conditional and idempotency semantics.

**Tóm lại:** Functional WebFlux không chỉ là cú pháp lambdas thay `@RestController`. Cốt lõi của nó là **hợp đồng bất đồng bộ hai tầng**: router tạo ra `Mono<HandlerFunction>`, handler tạo ra `Mono<ServerResponse>`, và body của response có thể là một `Publisher` riêng phát 0..N items. Đặt status/headers dựa trên completion/empty/error đúng thời điểm; dùng reactive I/O thực sự, không block event loop, và xác định routes/filters/security theo đúng layer.

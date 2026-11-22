# ServerHttpRequest, ServerHttpResponse và dữ liệu request/response trong Spring WebFlux

## 1. Vì sao cần hiểu hai giao diện HTTP cấp thấp?

Một controller Spring WebFlux thường nhận `@RequestBody`, `@RequestHeader`, `@RequestParam` rồi trả `Mono<DTO>` hoặc `ResponseEntity<DTO>`. Cách viết đó rất phù hợp cho API nghiệp vụ. Nhưng khi xây **WebFilter**, hạ tầng logging/tracing, gateway, custom error handling, response headers, streaming hoặc middleware cần can thiệp vào giao thức HTTP, bạn sẽ gặp hai abstraction:

- **`ServerHttpRequest`**: request đầu vào của server, từ method, URI, path, headers và cookies đến **body dạng `Flux<DataBuffer>`**.
- **`ServerHttpResponse`**: response server đang xây, gồm status, headers, cookies và các phương thức **ghi body bất đồng bộ** như `writeWith`, `writeAndFlushWith` và `setComplete`.

Trong WebFlux, hai đối tượng này được kết nối qua **`ServerWebExchange`** — ngữ cảnh của **một tương tác HTTP request/response**. Hiểu chúng giúp bạn tránh các lỗi khó thấy: đọc body hai lần, ghi status sau khi response đã commit, rò rỉ pooled buffers, trả request body qua thread blocking hoặc cache nhầm dữ liệu riêng tư.

Ví dụ đọc metadata:

~~~java
@GetMapping("/inspect")
public Mono<Map<String, String>> inspect(
        ServerHttpRequest request,
        ServerHttpResponse response) {

    response.getHeaders().set("Cache-Control", "no-store");
    String method = request.getMethod().name();
    String path = request.getPath().pathWithinApplication().value();

    return Mono.just(Map.of("method", method, "path", path));
}
~~~

Đây là **fragment** Spring WebFlux: cần đặt trong một `@RestController` cùng các imports. Không có câu lệnh blocking; Spring WebFlux có thể chọn converter để ghi JSON từ giá trị Mono. Response headers phải được đặt **trước khi response được commit**, không phải sau khi body gửi xong.

### Kết quả học tập

Sau bài bạn sẽ:
1. Phân biệt `ServerHttpRequest`, `ServerHttpResponse`, `ServerWebExchange`, `ServerRequest` và các đối tượng Servlet MVC.
2. Đọc method/URI/path/query/headers/cookies/client address mà không đánh đồng dữ liệu client với danh tính tin cậy.
3. Hiểu luồng body `Flux<DataBuffer>`: chỉ tiêu thụ có chủ đích, phối hợp codecs, giới hạn bộ nhớ, reference-counting và cancellation.
4. Ghi status, headers, `ResponseCookie` và body bằng các methods phản ứng của `ServerHttpResponse`.
5. Hiểu `beforeCommit`, `isCommitted` và khác biệt giữa `writeWith`, `writeAndFlushWith`, `setComplete`.
6. Dùng `WebFilter` để đặt exchange attributes, biến đổi request có kiểm soát, gắn response headers.
7. Viết ứng dụng Java 17 / Spring Boot 3.3.5 với endpoint metadata, JSON body, raw body bị giới hạn kích thước, cookies và response completion.
8. Kiểm bằng `WebTestClient` response cuối, bao gồm mã 201, 204, 413, echo bytes và headers.
9. Chẩn đoán các lỗi về security, content type, proxy headers, logging, body consumption và throughput.

Bài dùng **Spring WebFlux trên Reactor Netty**, không phải Servlet MVC. Các ví dụ runnable dùng Spring Framework 6.1.x do Spring Boot 3.3.5 quản lý; với Spring Framework 7, kiểm tài liệu API tương ứng.

## 2. Bức tranh kiến trúc HTTP trong WebFlux

~~~text
HTTP client
   |
   v
Reactor Netty / HTTP server adapter
   |
   v
ServerHttpRequest ---------+
                           |  ServerWebExchange
ServerHttpResponse --------+
   |
   v
WebFilter chain
   |
   v
WebHandler / DispatcherHandler
   |
   +-- HandlerMapping
   +-- HandlerAdapter (annotated / functional endpoints)
   +-- Codec: HttpMessageReader / HttpMessageWriter
   |
   v
ServerHttpResponse.writeWith / setComplete
   |
   v
HTTP client
~~~

Spring WebFlux triển khai một **`HttpHandler`** hướng framework-neutral để làm việc với Reactive HTTP server adapters; thường có `WebHttpHandlerBuilder` kết hợp WebFilter, WebExceptionHandler, session và các thành phần cần thiết. Lớp chọn handler có thể là `DispatcherHandler` cho annotated controllers hay functional routes.

### 2.1. Các package phải phân biệt

| Kiểu | Package quan trọng | Vai trò |
| --- | --- | --- |
| `ServerHttpRequest` | `org.springframework.http.server.reactive` | HTTP request server cấp thấp |
| `ServerHttpResponse` | `org.springframework.http.server.reactive` | HTTP response server cấp thấp |
| `ServerWebExchange` | `org.springframework.web.server` | Ngữ cảnh request + response + attributes + session |
| `WebFilter` | `org.springframework.web.server` | Middleware reactive trước/sau handler |
| `ServerRequest` | `org.springframework.web.reactive.function.server` | Request API tiện dùng cho functional WebFlux endpoint |
| `ServerResponse` | `org.springframework.web.reactive.function.server` | Response builder của functional WebFlux |
| `HttpServletRequest` | `jakarta.servlet.http` | Servlet stack, không phải WebFlux core |
| `org.springframework.web.servlet.function.ServerRequest` | Servlet WebMvc.fn | Functional Servlet MVC, **khác** reactive ServerRequest |

Trong cùng chương trình có thể có `WebClient`, nhưng `ClientRequest`/`ClientResponse` là abstraction **outbound client**, không phải hai đối tượng server đang nghiên cứu.

### 2.2. Vì sao ServerWebExchange quan trọng?

Một exchange cho phép truy cập:

~~~java
ServerHttpRequest request = exchange.getRequest();
ServerHttpResponse response = exchange.getResponse();
Map<String, Object> attributes = exchange.getAttributes();
~~~

Ngoài ra có `exchange.getSession()` trả `Mono<WebSession>`, thông tin principal `getPrincipal()`, locale, conditional request support như `checkNotModified(...)` và utilities khác. **Exchange attributes** là dữ liệu gắn với một request/response interaction; chúng không tự là global store hoặc user session.

Không lưu toàn bộ `ServerWebExchange` vào static collection hoặc queue dài hạn: exchange có thể giữ request body, response handles, headers, context và các tham chiếu ngoài vòng đời HTTP.

## 3. `ServerHttpRequest`: đọc các phần của request

### 3.1. HTTP method

~~~java
HttpMethod method = request.getMethod();
~~~

Đối tượng `HttpMethod` biểu diễn GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS... Đừng coi method là proof rằng request an toàn: một GET có tác dụng thay đổi dữ liệu do implementation sai vẫn có thể gây side effect; ngược lại POST có thể cần idempotency key và kiểm quyền.

### 3.2. URI và đường dẫn

~~~java
URI uri = request.getURI();
RequestPath path = request.getPath();
String relative = path.pathWithinApplication().value();
String fullPath = path.value();
~~~

Mã fragment cần `java.net.URI` và `org.springframework.http.server.RequestPath`. `getURI()` trả URI request theo server abstraction; `getPath()` là path API có thể xét context path. `pathWithinApplication()` thường dùng khi route application cần đường dẫn bên trong ứng dụng.

**Đừng tự parse path bằng `uri.toString().split("/")`**: encoded characters, context path, dấu `?`, slash normalization và gateway rewrites làm cách đó sai. Với annotated controller, `@PathVariable` thường thích hợp hơn trong business handler.

### 3.3. Query parameters

~~~java
MultiValueMap<String, String> query = request.getQueryParams();
String q = query.getFirst("q");
List<String> tags = query.get("tag");
~~~

`getQueryParams()` đã đưa tham số URI query vào một cấu trúc hỗ trợ nhiều giá trị cùng tên. Ví dụ:

~~~http
GET /api/search?q=java&tag=reactor&tag=spring HTTP/1.1
~~~

thì `q` là `"java"`, `tags` có hai phần tử. `getFirst` lấy giá trị đầu tiên, không có nghĩa những giá trị khác đã được validate.

**Quan trọng:** query string là dữ liệu không đáng tin. Giới hạn length/count, chuẩn hóa sort/filter values, validate và không đưa raw query vào SQL, logs có bí mật hoặc metric labels. Nếu client gửi `?role=admin`, điều đó không tự có giá trị phân quyền.

### 3.4. Request headers

~~~java
HttpHeaders headers = request.getHeaders();
MediaType contentType = headers.getContentType();
String language = headers.getFirst("Accept-Language");
String requestId = headers.getFirst("X-Request-Id");
~~~

`HttpHeaders` có thể chứa multi-value headers; `getFirst` chỉ đọc một giá trị. Header names theo HTTP không phân biệt hoa thường, nhưng header **values có semantics riêng**, ví dụ value của Authorization là credential bí mật.

Những headers quan trọng:

| Header | Ý nghĩa thông dụng | Thực hành an toàn |
| --- | --- | --- |
| `Content-Type` | Media type của request body | Kiểm phù hợp với codec/endpoint |
| `Accept` | Representation mà client có thể nhận | Dùng produces/negotiation khi cần |
| `Authorization` | Credential hoặc bearer token | Không log, xác thực qua Spring Security |
| `Cookie` | State client gửi | Không suy ra user/tenant chỉ bằng tên cookie |
| `Origin` | Browser origin cho CORS | CORS không thay authorization |
| `If-None-Match` | HTTP conditional request | Check ETag đúng tài nguyên/quyền |
| `Forwarded`, `X-Forwarded-*` | Metadata do proxy có thể thêm | Chỉ tin proxy chain được cấu hình |
| `Content-Length` | Declared body length nếu có | Không phải bằng chứng body thực tế sẽ đúng |
| `Traceparent` / correlation ID | Distributed tracing | Không dùng raw arbitrary values làm metric label |

### 3.5. Cookies

~~~java
MultiValueMap<String, HttpCookie> cookies = request.getCookies();
HttpCookie session = cookies.getFirst("SESSION");
~~~

`HttpCookie` chỉ mô tả cookie từ request. Session cookie có thể được kiểm bằng Spring Security/session management, nhưng controller không nên tự đọc `SESSION` rồi coi value là authenticated user.

Ví dụ demo sẽ chỉ trả **boolean có/không có cookie tên `demo`**, không đưa raw value vào JSON hoặc logs. Với dữ liệu thật, cookies mang authentication phải có HTTPS, `Secure`, `HttpOnly` và `SameSite` phù hợp threat model.

### 3.6. Client address và forwarded headers

~~~java
InetSocketAddress remote = request.getRemoteAddress();
InetSocketAddress local = request.getLocalAddress();
~~~

Đây là socket-layer information hoặc giá trị đã được adapter/transformer xử lý tùy hạ tầng. Sau CDN/reverse proxy, `getRemoteAddress()` có thể là địa chỉ proxy, **không nhất thiết client thật**. Đừng tin mọi `X-Forwarded-For` do client tự gửi, vì attacker có thể spoof IP.

Khi cần xây absolute URLs hoặc áp dụng IP allowlist/rate-limit, phải cấu hình trusted proxy/forwarded-header handling chính xác, giới hạn proxy chain được tin và kiểm ở ingress. Đừng tự lấy phần tử đầu tiên của `X-Forwarded-For` rồi coi đó là định danh chắc chắn.

### 3.7. Request ID

`request.getId()` cung cấp một ID để hỗ trợ đối chiếu logs cho request theo implementation. Không coi nó là durable transaction ID, session ID hoặc token bảo mật. Hệ tracing thường có trace/span IDs độc lập. Nếu dùng `request.getLogPrefix()` hoặc exchange log prefix, chúng phục vụ correlation, không biến một header do client gửi thành nguồn tin cậy.

## 4. Dữ liệu body không nằm trong `getHeaders()`

Trên WebFlux, `ServerHttpRequest.getBody()` trả:

~~~java
Flux<DataBuffer> body = request.getBody();
~~~

`DataBuffer` biểu diễn phần bytes do server adapter phát qua reactive stream. **Một DataBuffer không nhất thiết là một JSON object, HTTP chunk hay một message hoàn chỉnh.** TCP fragmentation, Netty read events và codec buffering có thể khiến body được cắt thành nhiều buffers tùy thời điểm.

Vì thế:
- Không giả định `getBody().next()` là **toàn bộ body**.
- Không đọc `getBody()` ở WebFilter rồi để controller `@RequestBody` đọc lại như thể `Flux` có khả năng replay mặc định.
- Không gọi `getBody().blockFirst()` trên event loop.
- Không dùng `buffer.collectList()` vô hạn cho user-upload không giới hạn.
- Không biến `DataBuffer` thành `String` bằng `buffer.toString()` mà không chỉ định cách decode, charset và release.
- Khi trực tiếp thao tác pooled `DataBuffer`, cần hiểu **quyền sở hữu/release** để tránh rò rỉ native memory.

### 4.1. Body thường được đọc đúng một lần

Trên socket HTTP thật, request body là **nguồn streaming**. Trong nhiều pipeline không có bảo đảm khả năng đọc lại sau lần consume đầu tiên. Ví dụ WebFilter logging:

~~~java
return DataBufferUtils.join(exchange.getRequest().getBody())
        .doOnNext(buffer -> logBody(buffer))
        .then(chain.filter(exchange));
~~~

Đây là **anti-pattern**, fragment có hàm `logBody` giả định. Nó có thể tiêu thụ body trước handler, làm mất dữ liệu controller cần; `join` không giới hạn có thể làm tăng memory; logging có thể lộ passwords/tokens; chưa kể reference-counted buffers cần release.

Nếu thực sự phải log/inspect body, cần request decorator phát **một stream có khả năng replay** được quản lý bộ nhớ và cleanup nghiêm ngặt, giới hạn bytes, redaction, cancellation và không bao giờ cache/log nội dung nhạy cảm tùy tiện. Thông thường chỉ log method/path/status/latency hoặc schema-level metadata là an toàn và đủ dùng hơn.

### 4.2. Vì sao codec cấp cao tốt hơn cho JSON?

Với annotated WebFlux controller:

~~~java
@PostMapping(
        path = "/api/notes",
        consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<NoteOut> create(@RequestBody Mono<NoteIn> input) {
    return input.map(this::convert);
}
~~~

Đây là fragment có `NoteIn`, `NoteOut`, `convert` chưa định nghĩa. Spring WebFlux dùng `HttpMessageReader`/JSON decoder để parse `Flux<DataBuffer>` thành đối tượng. Framework thường quản lý release/aggregation theo implementation, áp dụng memory limit codec, parse media type và truyền lỗi decoding đến error layer. Bạn vẫn cần Bean Validation hoặc validation domain rõ ràng.

**Không đọc `request.getBody()` trong một filter và `@RequestBody` lại trong controller** nếu chưa có lớp cache/decorator được thiết kế đúng. Cũng không tự subscribe request body ngoài pipeline bằng `subscribe()`.

## 5. `DataBuffer`: quản lý bytes và bộ nhớ

### 5.1. DataBuffer không chỉ là byte array

Spring cung cấp `DataBuffer` abstraction có `readableByteCount()`, `read(byte[])`, `write` và các chỉ số đọc/ghi. Tùy runtime, implementation có thể dựa trên Netty pooled `ByteBuf` với reference counting hoặc bộ nhớ heap. **Đừng assume GC Java sẽ tự giải phóng mọi direct/native buffers khi bạn đánh rơi reference.**

### 5.2. Cách nối body với giới hạn rõ

Khi thật sự cần một body nhỏ (ví dụ demo raw echo), có thể:

~~~java
Mono<byte[]> bytes = DataBufferUtils
        .join(request.getBody(), 1024)
        .map(buffer -> {
            try {
                byte[] copy = new byte[buffer.readableByteCount()];
                buffer.read(copy);
                return copy;
            } finally {
                DataBufferUtils.release(buffer);
            }
        })
        .defaultIfEmpty(new byte[0]);
~~~

Đây là fragment dùng `ServerHttpRequest request` và imports `DataBufferUtils`/`Mono`. `join(...,1024)` giới hạn số bytes được tổng hợp; quá giới hạn phát `DataBufferLimitException`. Nếu stream lỗi/hủy trước khi joined buffer phát ra, `join` chịu trách nhiệm release phần đã tích lũy theo contract; khi nhận thành công một joined buffer để tự đọc, đoạn `finally` **release kết quả**.

Nếu nội dung có thể lớn, **không** gom tất cả vào `byte[]`. Với file upload, sử dụng streaming resource/`FilePart.transferTo`, storage API phù hợp, server/gateway limits và validation trên luồng.

### 5.3. Chuyển buffer sang String phải biết charset

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Fragment này giả định `bytes` là `byte[]` đã được copy đúng. Không decode từng DataBuffer bằng UTF-8 rồi nối String nếu một multi-byte character bị cắt giữa buffers: decoder phải xử lý boundary đúng hoặc aggregate trong giới hạn. Với JSON/text, thường để codec của Spring làm việc này.

### 5.4. Release / retain / ownership

- Khi bạn **nhận và tiêu thụ** một pooled `DataBuffer` ở application level (không chuyển cho framework writer), bạn có thể cần `DataBufferUtils.release(buffer)`.
- Nếu bạn đưa publishers/buffers trực tiếp vào `response.writeWith(...)`, response writer quản lý luồng ghi và quyền sở hữu theo contract; không release trước khi body được viết xong.
- Nếu bạn muốn replay/copy/slice shared pooled buffers, việc `retain`/`release` cần cân bằng theo lifecycle; đừng giữ reference khi nguồn đã release.
- Trên error/cancel, phải kiểm resource cleanup ở các operators; `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` có thể có ích ở pipeline cụ thể, nhưng không thêm cơ học khi một thành phần khác đang sở hữu buffer.
- Không viết mã vừa release buffer trong `doOnNext` **vừa** chuyển cùng object xuống `writeWith`: có thể gây use-after-release.

**Ranh giới rõ:** body bytes được copy thành `byte[]` trong demo; sau khi release joined buffer, ứng dụng sử dụng **bản sao** để tạo response buffer mới.

### 5.5. Giới hạn body: nhiều tầng khác nhau

| Giới hạn | Tầng áp dụng | Lưu ý |
| --- | --- | --- |
| Reverse proxy/CDN maximum request body | Infrastructure | Có thể chặn request trước khi vào Spring |
| Reactor Netty server config | HTTP server | Các giới hạn liên quan decoder/headers/form behavior |
| `spring.codec.max-in-memory-size` | Codec aggregation | Áp dụng cho một số codec/buffer decode, không phải mọi custom raw pipeline |
| `DataBufferUtils.join(body,maxByteCount)` | Code tự aggregate | Bảo vệ lần gom buffer cụ thể |
| Validation DTO/payload | Domain/service | Giới hạn field count, string length, types |
| Multipart/file storage limits | Upload pipeline | Chú ý disk quota, temporary files, streaming |

**Không tin mỗi header `Content-Length`** để bảo vệ memory: client có thể dùng chunked transfer hoặc gửi sai/trùng thông tin, tùy HTTP server xử lý. Giới hạn phải được áp dụng trong quá trình đọc và ở infrastructure.

## 6. `ServerHttpResponse`: một response có vòng đời commit

`ServerHttpResponse` cho phép:
- `setStatusCode(HttpStatusCode)`: chọn HTTP status nếu response chưa commit; trả boolean biểu thị khả năng set trong API.
- `getStatusCode()`: trạng thái hiện tại có thể null nếu chưa set tường minh, tùy abstraction.
- `getHeaders()`: thêm/sửa response headers trước commit.
- `getCookies()` và `addCookie(ResponseCookie)`: outbound cookies.
- `beforeCommit(Supplier<Mono<Void>>)`: đăng ký hành động trước commit.
- `isCommitted()`: response đã ở trạng thái committed theo abstraction?
- `bufferFactory()`: tạo DataBuffer cho output.
- `writeWith(Publisher<? extends DataBuffer>)`: ghi body reactive.
- `writeAndFlushWith(Publisher<? extends Publisher<? extends DataBuffer>>)`: ghi các nhóm buffers và flush theo mức publisher bên trong.
- `setComplete()`: đánh dấu output hoàn tất, không có body tự tạo.

### 6.1. Status và headers nên được quyết định sớm

~~~java
response.setStatusCode(HttpStatus.ACCEPTED);
response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
response.getHeaders().setCacheControl("no-store");
~~~

Đây là fragment với response trong controller/filter. Gọi `setStatusCode` không tự viết ngay bytes xuống socket; việc commit xảy ra khi publisher response được xử lý. **Một khi response đã commit, không thể tin rằng thay status hay headers sẽ có hiệu lực.** Trong ứng dụng đa filter, luôn kiểm response cuối bằng integration test.

### 6.2. `ResponseCookie` không giống request `HttpCookie`

Để gửi cookie:

~~~java
ResponseCookie cookie = ResponseCookie.from("demo", "ok")
        .path("/")
        .httpOnly(true)
        .sameSite("Lax")
        .build();

response.addCookie(cookie);
~~~

Trên HTTPS production, nếu cookie cần đi qua TLS, cân nhắc `secure(true)` và cookie scope/domain/path. `HttpOnly` làm JavaScript không đọc cookie qua document.cookie; `SameSite` ảnh hưởng browser cross-site sending; **không cái nào thay authentication/authorization và CSRF protection**.

Đừng viết cookie bearer token hoặc session ID vào URL để debug. Headers `Set-Cookie` có thể lộ bí mật nếu log raw; lọc/redact chúng ở proxies và application logging.

### 6.3. `beforeCommit` chạy vào lúc nào?

~~~java
response.beforeCommit(() ->
        Mono.fromRunnable(() ->
                response.getHeaders().set("X-Commit", "ready")));
~~~

`beforeCommit` **đăng ký hành động**, không có nghĩa thực thi ngay. Callback nên trả một `Mono<Void>` **được defer** (ví dụ `Mono.fromRunnable` hoặc `Mono.defer`), vì response commit machinery sẽ subscribe đúng thời điểm và đúng thứ tự với callbacks khác. Nếu làm side-effect ngay khi tạo supplier hoặc trả một Mono đã eager complete, bạn có thể ghi header sai thời điểm.

**Đừng gọi `block()`, DB/JDBC synchronous, HTTP client đồng bộ hoặc sleep trong beforeCommit callback**: nó có thể đang chạy trong I/O/event-loop thread. Chỉ thực hiện việc nhẹ, deterministic và không cần network.

### 6.4. `isCommitted` không phải công cụ rollback

~~~java
if (!response.isCommitted()) {
    response.setStatusCode(HttpStatus.BAD_REQUEST);
}
~~~

Kiểm tra này có thể hữu ích để quyết định xử lý lỗi, nhưng race vẫn có thể xảy ra khi luồng response đang commit. Không dùng nó để hứa rằng status đổi chắc chắn thành công; `setStatusCode` có kết quả boolean và response writes/errors cần được điều phối theo pipeline.

Một khi HTTP headers/body đã gửi đi, bạn thường **không thể** thay status 200 thành 500 rồi ghi JSON ProblemDetail tùy ý; đặc biệt với SSE và streaming response.

### 6.5. `setComplete()`

~~~java
response.setStatusCode(HttpStatus.NO_CONTENT);
return response.setComplete();
~~~

Phù hợp response **204 No Content** không có body. `setComplete()` trả `Mono<Void>`, phải **return** cho WebFlux hoặc compose vào pipeline để framework thực thi. Chỉ gọi method rồi bỏ qua Mono chưa bảo đảm work hoàn tất.

## 7. Ghi response body: `writeWith` và `writeAndFlushWith`

### 7.1. `writeWith`

~~~java
byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
response.getHeaders().setContentType(
        new MediaType("text", "plain", StandardCharsets.UTF_8));

return response.writeWith(Mono.fromSupplier(
        () -> response.bufferFactory().wrap(bytes)));
~~~

Fragment này thuộc handler trả `Mono<Void>`. `Mono.fromSupplier` trì hoãn việc tạo output buffer đến subscription; `writeWith` nhận publisher của DataBuffer và ghi ra HTTP transport.

Không cần `subscribe()` hay `block()`; controller trả Mono để WebFlux quản lý lifecycle. Nếu truyền `Flux<DataBuffer>` từ request input sang response output, cần biết ai sở hữu/releases từng buffer và có giới hạn body phù hợp.

### 7.2. `writeAndFlushWith`

Khi output có nhiều nhóm buffers và bạn muốn điều khiển các flush boundaries theo nested publishers:

~~~java
Flux<Publisher<DataBuffer>> groups = ...;
return response.writeAndFlushWith(groups);
~~~

Đây là **pseudocode** với `groups` chưa được định nghĩa; không phải yêu cầu sử dụng khi trả JSON thông thường. Nó thích hợp hơn cho một số trường hợp streaming; nhưng flushing phụ thuộc server/transport và không cam kết mỗi item đến client thành một TCP packet riêng.

Đừng dùng writeAndFlushWith cho một response JSON nhỏ chỉ vì tên có chữ “flush”. HTTP codecs hoặc WebFlux `ResponseEntity<Flux<...>>`/SSE có thể là API phù hợp hơn cho streaming ở controller.

### 7.3. `Mono<Void>`, `Mono<T>` và `ResponseEntity`

| Handler return type | Ai quyết định body/status? |
| --- | --- |
| `Mono<DTO>` | WebFlux chọn writer/codec, thường status 200 nếu thành công |
| `Mono<ResponseEntity<DTO>>` | Khi Mono emit, status, headers, body từ ResponseEntity được áp dụng |
| `ResponseEntity<Mono<DTO>>` | Status/headers có sẵn sớm hơn, body bất đồng bộ |
| `Mono<Void>` sau `ServerHttpResponse.writeWith(...)` | Application tự ghi body vào response |
| `Mono<Void>` sau `ServerHttpResponse.setComplete()` | Application hoàn tất response không có body |

Đừng trộn hai chủ sở hữu response: nếu controller đã gọi `response.writeWith`, đừng đồng thời trả `Mono<ResponseEntity<?>>` từ cùng method để có hai luồng cố ghi body/status. Hãy chọn **một** cách.

## 8. `ServerWebExchange` và request attributes

Một filter có thể đặt metadata **chỉ cho request này**:

~~~java
exchange.getAttributes().put("demo.observed", Boolean.TRUE);
return chain.filter(exchange);
~~~

Handler sau đó đọc:

~~~java
Boolean observed =
        exchange.getAttribute("demo.observed");
~~~

Attributes là Map trong exchange:
- Phù hợp đánh dấu đã kiểm tra request, correlation metadata hoặc routing state nội bộ.
- Không tự được gửi sang client; muốn response header phải set riêng.
- Không giống session hoặc cookie; không sống qua nhiều request độc lập.
- Không giống `Reactor Context`: việc một reactive subscription đổi thread không tự biến attribute thành ThreadLocal.
- Không phải nơi an toàn để cache nhiều bytes hoặc secrets; đừng giữ body copies không giới hạn.

### 8.1. WebSession khác exchange attributes

`exchange.getSession()` trả `Mono<WebSession>`. WebSession có lifecycle/persistence riêng tùy configured store. Chỉ **truy cập** session không nhất thiết tạo session mới với cookie ngay; việc ghi attributes/khởi tạo session mới có thể làm phát sinh persistence/cookie. Đừng dùng request-scoped attributes để thay session, và đừng dùng session làm cache toàn bộ HTTP body.

### 8.2. Principal/security context

`exchange.getPrincipal()` trả reactive principal của request theo security integration. Với Spring Security Reactive, `ReactiveSecurityContextHolder` và Reactor Context mới là vị trí đáng tin để truy cập authentication đúng pipeline. Không tự gán principal bằng một `X-User` header trừ khi header chỉ đến từ trusted authentication proxy với chain được bảo vệ và verified.

## 9. `WebFilter`: cắt ngang HTTP request/response một cách an toàn

`WebFilter` có signature:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
~~~

Nó hoạt động quanh handler và có thể:
- Kiểm metadata method/path/header trước handler.
- Đặt exchange attributes.
- Chỉnh response headers **trước commit**.
- Tạo response ngắn và dừng chain khi có một quyết định được phép tại layer này.
- Đo duration với `doFinally` mà không cần block.

### 9.1. Cách gắn response header đúng commit phase

~~~java
@Bean
WebFilter traceFilter() {
    return (exchange, chain) -> {
        exchange.getAttributes().put("demo.observed", true);

        exchange.getResponse().beforeCommit(() ->
                Mono.fromRunnable(() ->
                        exchange.getResponse().getHeaders().set(
                                "X-Demo-Filter", "observed")));

        return chain.filter(exchange);
    };
}
~~~

Code này gần hoàn chỉnh, cần imports `@Bean`, `WebFilter` và `Mono`/class `@Configuration` ở demo. **Không đọc body ở filter**; response header được set khi commit nên áp dụng cả response bình thường và nhiều error responses nếu commit còn có thể làm được.

### 9.2. Vì sao `then(Mono.fromRunnable(...))` có thể quá muộn?

Một pattern dễ sai:

~~~java
return chain.filter(exchange)
        .then(Mono.fromRunnable(() ->
                exchange.getResponse().getHeaders()
                        .set("X-Late-Header", "value")));
~~~

Với nhiều handlers, chain hoàn thành **sau khi response đã được ghi/commit**, vì vậy viết header ở `then` có thể không còn tác dụng hoặc gặp trạng thái read-only. Muốn header ngay trước commit, dùng `beforeCommit`.

### 9.3. Không xử lý body tùy tiện ở filter

Muốn chỉnh request headers/URI bằng một request wrapper, có thể dùng builder:

~~~java
ServerHttpRequest request = exchange.getRequest().mutate()
        .header("X-Internal-Demo", "checked")
        .build();

ServerWebExchange updated =
        exchange.mutate().request(request).build();

return chain.filter(updated);
~~~

Đây là fragment thuộc WebFilter; chỉ gắn header nội bộ khi bạn có trust boundary rõ. Đối với header đã tồn tại và không đáng tin, hãy **remove/replace** theo API phù hợp thay vì thêm một giá trị thứ hai rồi tin `getFirst`: duplicate headers có thể gây request smuggling hoặc nhầm identity nếu mỗi tầng chọn một value khác nhau.

Để **đổi body** thực sự, cần `ServerHttpRequestDecorator` override `getBody()` cùng buffer retain/release, backpressure, content length và cleanup đúng. Không thay body mà giữ `Content-Length` cũ hoặc content encoding không tương thích.

### 9.4. Filter order và Spring Security

Ứng dụng có Spring Security reactive sẽ có `SecurityWebFilterChain` và các WebFilters cần thứ tự rõ. Filter tự tạo không được coi là thay thế authorization/CSRF/CORS. Việc decorate request/response không tự thay quyền của user.

Nếu filter tự trả 401/403, phải bảo đảm response format, auth challenge, correlation header và không leak private details; tốt hơn dùng Spring Security exception handlers/entry points đúng trách nhiệm.

## 10. Servlet và WebFlux: những điểm tương tự dễ nhầm

| Chủ đề | Servlet MVC | WebFlux |
| --- | --- | --- |
| Request low-level | `HttpServletRequest` | `ServerHttpRequest` |
| Response low-level | `HttpServletResponse` | `ServerHttpResponse` |
| Chỗ nối request/response | Servlet request + response arguments | `ServerWebExchange` |
| Body | `ServletInputStream` hoặc argument resolver | `Flux<DataBuffer>` hoặc reactive codecs |
| Filter | `jakarta.servlet.Filter` | `WebFilter` |
| Controller input body | `@RequestBody DTO` | `@RequestBody Mono<DTO>` hoặc DTO tùy contract |
| Body response low-level | `ServletOutputStream` | `writeWith(Publisher<DataBuffer>)` |
| Completion | Servlet return/async lifecycle | `Mono<Void>` hoàn tất |
| Buffer ownership | Servlet streams/server implementation | DataBuffer lifecycle cần chú ý release |
| Async dispatch | Servlet `DispatcherType.ASYNC` có thể áp dụng | Reactor/Reactive server pipeline, không đồng nhất với MVC async dispatch |

Không import `org.springframework.web.servlet.function.ServerRequest` vào WebFlux hoặc cố tạo `HttpServletRequest` ở một ứng dụng Reactor Netty không có Servlet container.

**Một điểm đáng nhớ:** "Reactive HTTP server" không có nghĩa bạn được phép xử lý body blocking bằng `.block()`. `ServerHttpRequest.getBody().collectList().block()` trên event loop vừa chặn thread vừa gom memory không giới hạn.

## 11. Ví dụ hoàn chỉnh: Spring Boot 3.3.5 / Java 17 / WebFlux

Ứng dụng demo có năm routes:
1. `GET /api/request`: đọc method, path, query `q`, kiểm có custom header/cookie, đọc exchange attribute do WebFilter đặt; response có `Cache-Control: no-store`.
2. `POST /api/notes`: body JSON thành record qua `@RequestBody Mono<NoteInput>`, trả HTTP 201 với DTO, không đọc raw DataBuffer.
3. `POST /api/raw-echo`: đọc `ServerHttpRequest.getBody()` **có giới hạn 1024 bytes**, copy rồi release joined DataBuffer; tạo response body UTF-8 bằng `ServerHttpResponse.writeWith`, trả 413 nếu vượt.
4. `GET /api/commit`: đặt status 204, `beforeCommit` thêm header, `setComplete` trả Mono.
5. `GET /api/cookie`: dùng `ResponseCookie` để phát Set-Cookie với HttpOnly, SameSite và Path.

Mỗi route được WebFilter gắn `X-Demo-Filter: observed` vào thời điểm commit. Dữ liệu demo không cần database, tài khoản hoặc network dependency. Không thêm Spring Security starter trong project ví dụ; **production cần security phù hợp**.

~~~text
webflux-http-foundation/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/httpfoundation/
    │   ├── HttpFoundationApplication.java
    │   ├── web/ExchangeObservationFilter.java
    │   └── web/HttpFoundationController.java
    └── test/java/com/example/httpfoundation/
        └── HttpFoundationIntegrationTest.java
~~~

### 11.1. Gradle build

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-http-foundation'
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

Chỉ dùng `spring-boot-starter-webflux`, không thêm `spring-boot-starter-web`. Nếu cả hai starters có mặt, Boot có thể chọn MVC application type theo mặc định; điều đó làm sai mục tiêu demo Reactor Netty WebFlux.

### 11.2. Main application

`src/main/java/com/example/httpfoundation/HttpFoundationApplication.java`:

~~~java
package com.example.httpfoundation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpFoundationApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpFoundationApplication.class, args);
    }
}
~~~

### 11.3. WebFilter ghi exchange attribute và header trước commit

`src/main/java/com/example/httpfoundation/web/ExchangeObservationFilter.java`:

~~~java
package com.example.httpfoundation.web;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class ExchangeObservationFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        exchange.getAttributes().put("demo.observed", Boolean.TRUE);

        exchange.getResponse().beforeCommit(() ->
                Mono.fromRunnable(() ->
                        exchange.getResponse().getHeaders().set(
                                "X-Demo-Filter", "observed")));

        return chain.filter(exchange);
    }
}
~~~

Filter này **không** đụng body, không block, không tự subscribe. Nó đặt marker vào exchange và đăng ký callback ghi header trước commit. Trong ứng dụng thật, nếu filter cần quan sát status/timeouts, cân nhắc `doFinally`, tracing libraries và bảo đảm correlation data không chứa secrets.

### 11.4. Controller: request metadata, JSON body, bounded raw body, commit, cookie

`src/main/java/com/example/httpfoundation/web/HttpFoundationController.java`:

~~~java
package com.example.httpfoundation.web;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class HttpFoundationController {

    public record RequestSnapshot(
            String method, String path, String query,
            boolean hasDemoHeader, boolean hasDemoCookie,
            boolean observed) {}

    public record NoteInput(String text) {}

    public record NoteOutput(String text, int length) {}

    @GetMapping(path = "/request",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<RequestSnapshot> inspect(ServerWebExchange exchange) {
        ServerHttpRequest request = exchange.getRequest();
        ServerHttpResponse response = exchange.getResponse();

        String q = request.getQueryParams().getFirst("q");
        String safeQuery = q == null ? ""
                : q.substring(0, Math.min(q.length(), 64));

        response.getHeaders().setCacheControl("no-store");

        return Mono.just(new RequestSnapshot(
                request.getMethod().name(),
                request.getPath().pathWithinApplication().value(),
                safeQuery,
                request.getHeaders().containsKey("X-Demo-Client"),
                request.getCookies().containsKey("demo"),
                Boolean.TRUE.equals(
                        exchange.getAttribute("demo.observed"))));
    }

    @PostMapping(path = "/notes",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<NoteOutput>> notes(
            @RequestBody Mono<NoteInput> input) {

        return input.map(note -> {
            String text = note.text();
            if (text == null || text.isBlank()
                    || text.length() > 120) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Invalid note text");
            }

            String normalized = text.trim();
            NoteOutput output =
                    new NoteOutput(normalized, normalized.length());

            return ResponseEntity.created(URI.create("/api/notes/1"))
                    .header(HttpHeaders.CACHE_CONTROL, "no-store")
                    .body(output);
        });
    }

    @PostMapping(path = "/raw-echo",
            consumes = MediaType.TEXT_PLAIN_VALUE)
    public Mono<Void> rawEcho(
            ServerHttpRequest request, ServerHttpResponse response) {

        response.getHeaders().setContentType(
                new MediaType(
                        "text", "plain", StandardCharsets.UTF_8));
        response.getHeaders().setCacheControl("no-store");

        Mono<byte[]> content =
                DataBufferUtils.join(request.getBody(), 1024)
                        .map(buffer -> {
                            try {
                                byte[] bytes =
                                        new byte[buffer.readableByteCount()];
                                buffer.read(bytes);
                                return bytes;
                            } finally {
                                DataBufferUtils.release(buffer);
                            }
                        })
                        .defaultIfEmpty(new byte[0]);

        return content
                .flatMap(bytes -> response.writeWith(
                        Mono.fromSupplier(() ->
                                response.bufferFactory().wrap(bytes))))
                .onErrorResume(DataBufferLimitException.class, error -> {
                    response.setStatusCode(
                            HttpStatus.valueOf(413));
                    return response.setComplete();
                });
    }

    @GetMapping("/commit")
    public Mono<Void> commit(ServerHttpResponse response) {
        response.setStatusCode(HttpStatus.NO_CONTENT);
        response.beforeCommit(() ->
                Mono.fromRunnable(() ->
                        response.getHeaders().set(
                                "X-Commit-Phase", "ready")));
        return response.setComplete();
    }

    @GetMapping("/cookie")
    public Mono<Void> cookie(ServerHttpResponse response) {
        response.addCookie(ResponseCookie.from("demo", "ok")
                .path("/")
                .httpOnly(true)
                .sameSite("Lax")
                .build());
        response.setStatusCode(HttpStatus.NO_CONTENT);
        return response.setComplete();
    }
}
~~~

### 11.5. Giải thích đúng ownership trong raw echo

`rawEcho` là phần quan trọng nhất:
1. Chỉ endpoint này gọi `request.getBody()` trực tiếp; không có `@RequestBody` cạnh tranh cùng body.
2. `DataBufferUtils.join(...,1024)` giới hạn aggregate bytes. Quá 1024 có thể gây `DataBufferLimitException`.
3. `map(buffer -> {... finally release(buffer)})` **copy** bytes ra mảng Java rồi giải phóng joined DataBuffer.
4. `response.writeWith(Mono.fromSupplier(...wrap(bytes)))` tạo một **output buffer mới** và để response writer tiêu thụ.
5. Khi body trống, `defaultIfEmpty(new byte[0])` bảo đảm có đường kết thúc phù hợp, không cố viết JSON.
6. Nếu aggregation vượt giới hạn trước response commit, `onErrorResume` chọn 413 và complete response.
7. Không tự gọi `subscribe`, `block` hoặc `Thread.sleep`; Spring quản lý reactive lifecycle.
8. Đây là ví dụ cho **body nhỏ**. Với file upload/streaming thật, không aggregate lên heap, không echo thông tin nhạy cảm, dùng storage/stream APIs có request-size limits ở ingress và application.

**Lưu ý về Java memory:** copy sang `byte[]` nghĩa là dữ liệu vẫn tạm tồn tại trong heap, dù pooled buffer gốc được release. Không giữ hoặc log byte array nếu chứa credentials/PII. `no-store` ở response chỉ yêu cầu HTTP caches tuân thủ không lưu, không tự xóa mọi bản copy ở heap/application stores.

### 11.6. Vì sao `@RequestBody Mono<NoteInput>` không cần DataBufferUtils.join?

Ở `/api/notes`, WebFlux JSON reader parse body giúp bạn. Bạn chỉ thao tác DTO:
- `@RequestBody Mono<NoteInput>` nhận JSON asynchronous.
- Input không hợp lệ sẽ phát lỗi từ decoder hoặc từ `ResponseStatusException` trong `map`.
- `ResponseEntity.created(...)` đặt 201, Location và Cache-Control rõ; không gọi `ServerHttpResponse.writeWith` thủ công.
- Vì demo không có DB, Location `/api/notes/1` chỉ là minh họa contract, **không tồn tại một endpoint GET notes/1**. Trong production không trả 201/Location giả mà không lưu tài nguyên; cần repository và ID thực, hoặc chọn response khác.

Nếu muốn validation tự động, có thể dùng Bean Validation với Spring validation starter và `@Valid` cho DTO, nhưng cần test input constraints, media type và error schema. Ở demo logic kiểm text ngắn gọn và không cần thêm dependency.

### 11.7. Vì sao `/api/commit` dùng 204 và không ghi body?

HTTP 204 No Content không nên chứa response payload. `setComplete` trả Mono để Spring thực thi commit, gọi `beforeCommit` và hoàn tất. Gọi `writeWith` song song với `setComplete` trên cùng response sẽ tạo hai paths tranh nhau commit; tránh điều đó.

### 11.8. Cookie an toàn còn phụ thuộc HTTPS và auth

Cookie demo tên `demo` không chứa secret; `httpOnly(true)` và `sameSite("Lax")` chỉ minh họa response cookie builder. Với session cookie trên HTTPS production, thường cần `secure(true)`, policy SameSite đúng cross-site flows, rotation, expiration và CSRF protection phù hợp. Đừng tin client có cookie thì tự có quyền đọc tài nguyên.

## 12. Kiểm thử WebFlux với WebTestClient

`WebTestClient` là test HTTP client phù hợp Spring WebFlux, có thể bind vào application context hoặc kết nối embedded server. Ở đây dùng `RANDOM_PORT` để yêu cầu đi qua Reactor Netty thực, giúp kiểm response body/headers sau commit.

`src/test/java/com/example/httpfoundation/HttpFoundationIntegrationTest.java`:

~~~java
package com.example.httpfoundation;

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
class HttpFoundationIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void inspectUsesRequestMetadataAndExchangeAttribute() {
        client.get().uri("/api/request?q=hello")
                .header("X-Demo-Client", "yes")
                .cookie("demo", "ok")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals(HttpHeaders.CACHE_CONTROL, "no-store")
                .expectHeader()
                    .valueEquals("X-Demo-Filter", "observed")
                .expectBody()
                .jsonPath("$.method").isEqualTo("GET")
                .jsonPath("$.path").isEqualTo("/api/request")
                .jsonPath("$.query").isEqualTo("hello")
                .jsonPath("$.hasDemoHeader").isEqualTo(true)
                .jsonPath("$.hasDemoCookie").isEqualTo(true)
                .jsonPath("$.observed").isEqualTo(true);
    }

    @Test
    void jsonBodyIsDecodedAndResponseStatusIs201() {
        client.post().uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("text", "Spring WebFlux"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader()
                    .valueEquals(HttpHeaders.LOCATION, "/api/notes/1")
                .expectHeader()
                    .valueEquals(HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody()
                .jsonPath("$.text").isEqualTo("Spring WebFlux")
                .jsonPath("$.length").isEqualTo(14);
    }

    @Test
    void invalidJsonDomainValueIsRejected() {
        client.post().uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("text", "  "))
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void smallRawBodyIsCopiedAndReturned() {
        client.post().uri("/api/raw-echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN)
                .expectBody(String.class).isEqualTo("hello");
    }

    @Test
    void rawBodyLimitIsEnforced() {
        client.post().uri("/api/raw-echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("a".repeat(1200))
                .exchange()
                .expectStatus().isEqualTo(413);
    }

    @Test
    void beforeCommitRunsAndNoContentHasNoBody() {
        client.get().uri("/api/commit")
                .exchange()
                .expectStatus().isNoContent()
                .expectHeader()
                    .valueEquals("X-Commit-Phase", "ready")
                .expectHeader()
                    .valueEquals("X-Demo-Filter", "observed")
                .expectBody().isEmpty();
    }

    @Test
    void responseCookieContainsSecurityAttributes() {
        client.get().uri("/api/cookie")
                .exchange()
                .expectStatus().isNoContent()
                .expectHeader().valueMatches(
                        HttpHeaders.SET_COOKIE, ".*demo=ok.*")
                .expectHeader().valueMatches(
                        HttpHeaders.SET_COOKIE, ".*HttpOnly.*")
                .expectHeader().valueMatches(
                        HttpHeaders.SET_COOKIE, ".*SameSite=Lax.*");
    }
}
~~~

**Kiểm về độ chính xác test:** `"Spring WebFlux"` có 14 ký tự UTF-16 (`6 + 1 + 7`) nên `length` dự kiến 14. Nếu đổi nội dung input, phải cập nhật expected length theo Java `String.length()`; đó không phải byte length UTF-8 khi có dấu tiếng Việt. Không assert header order, timestamp hoặc server-generated ID.

Chạy ở project có Gradle wrapper tương thích Java 17:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

Test không chứng minh under-load performance hoặc proxy configuration. Nó xác minh contracts của application trên embedded server. Để kiểm uploads thực, security, retries/cancellation hoặc streaming clients, cần integration/load tests riêng.

## 13. Quan sát bằng curl

Khởi động project bằng `./gradlew bootRun` và gọi:

### 13.1. Metadata endpoint

~~~bash
curl -i 'http://localhost:8080/api/request?q=java' \
  -H 'X-Demo-Client: yes' \
  -H 'Cookie: demo=ok'
~~~

Dự kiến HTTP 200, JSON dạng:

~~~json
{
  "method": "GET",
  "path": "/api/request",
  "query": "java",
  "hasDemoHeader": true,
  "hasDemoCookie": true,
  "observed": true
}
~~~

Headers quan trọng:

~~~http
Cache-Control: no-store
X-Demo-Filter: observed
Content-Type: application/json
~~~

Response có thể thêm headers khác, nén hoặc truyền chunked tùy server. Không dựa vào thứ tự JSON fields hay headers.

### 13.2. Tạo JSON note

~~~bash
curl -i -X POST 'http://localhost:8080/api/notes' \
  -H 'Content-Type: application/json' \
  -d '{"text":"Spring WebFlux"}'
~~~

Dự kiến 201 Created, `Location: /api/notes/1`, `Cache-Control: no-store` và body:

~~~json
{"text":"Spring WebFlux","length":14}
~~~

Đây là **demo không persistence**, nên đừng sao chép y nguyên Location cố định này cho production: dùng repository tạo resource thật hoặc đổi semantics/status.

### 13.3. Raw body echo và 413

~~~bash
curl -i -X POST 'http://localhost:8080/api/raw-echo' \
  -H 'Content-Type: text/plain' \
  --data-binary 'hello'
~~~

Kết quả 200 body text:

~~~text
hello
~~~

Nếu body vượt 1024 bytes, Spring code chủ động đặt HTTP 413. Có thể tạo file lớn bằng công cụ tùy hệ điều hành để kiểm (không cần gửi dữ liệu riêng tư). Giới hạn ở demo **không** đại diện cho toàn bộ request-size policies của product.

### 13.4. Commit và cookie

~~~bash
curl -i 'http://localhost:8080/api/commit'
curl -i 'http://localhost:8080/api/cookie'
~~~

`/api/commit` trả 204, header `X-Commit-Phase: ready`, `X-Demo-Filter: observed` và không có body.

`/api/cookie` trả 204 cùng `Set-Cookie` có `demo=ok`, `Path=/`, `HttpOnly` và `SameSite=Lax`. Cookie demo không có `Secure` vì ví dụ chạy plain HTTP localhost. Trong sản phẩm HTTPS/session thực, bảo đảm chính sách bảo mật bổ sung.

## 14. Những lỗi nghiêm trọng nhất khi thao tác dữ liệu request/response

### 14.1. Đọc request body hai lần

**Sai:**

~~~java
return DataBufferUtils.join(request.getBody())
        .doOnNext(this::logRaw)
        .then(chain.filter(exchange));
~~~

Sau khi filter consume, handler có thể nhận body trống, decoder lỗi hoặc lifecycle phức tạp. Fragment còn thiếu release và giới hạn bytes. **Sửa:** không log raw body; nếu bắt buộc, dùng custom decorator có replay/buffer ownership được test kỹ, redaction và limits.

### 14.2. `subscribe()` bên trong WebFilter

~~~java
exchange.getRequest().getBody().subscribe(this::auditBuffer);
return chain.filter(exchange);
~~~

**Sai** vì tách một subscription ngoài HTTP request lifecycle; nguồn request có thể bị consume/race, error/cancel khó quản lý và audit không bảo đảm bền vững. Đừng dùng `subscribe` như một cách "trộm xem" HTTP body. Hãy compose đúng trong Mono/Flux của chain.

### 14.3. Buffer không release khi tự tiêu thụ

~~~java
request.getBody().map(buffer -> {
    byte[] bytes = new byte[buffer.readableByteCount()];
    buffer.read(bytes);
    return bytes;
});
~~~

Code fragment trên không release pooled `DataBuffer`; trong Netty có nguy cơ memory leak. Khi đã lấy quyền xử lý buffer, phải dùng `DataBufferUtils.release` theo đúng ownership, thường trong `finally` và xử lý cancellation/discard phù hợp.

### 14.4. Release buffer trước khi writer dùng

~~~java
Flux<DataBuffer> broken = request.getBody()
        .doOnNext(DataBufferUtils::release);
return response.writeWith(broken);
~~~

**Sai**: writer có thể đọc một buffer đã release. Khi forward raw body trực tiếp, publisher ownership và lifecycle cần nhất quán; không gọi release ở nhánh upstream rồi lại chuyển cùng buffer cho downstream writer.

### 14.5. Ghi header sau `chain.filter(...)` đã hoàn tất

~~~java
return chain.filter(exchange).then(
        Mono.fromRunnable(() ->
                exchange.getResponse().getHeaders()
                        .set("X-Late", "value")));
~~~

Có thể quá trễ do response đã commit. Dùng `response.beforeCommit(() -> Mono.fromRunnable(...))` trước khi gọi chain.

### 14.6. Đặt status nhưng không return Mono ghi/complete

~~~java
response.setStatusCode(HttpStatus.NO_CONTENT);
response.setComplete();
return Mono.empty();
~~~

Mã này bỏ qua `Mono<Void>` được trả từ `setComplete`; có thể hoạt động phụ thuộc framework bên ngoài nhưng **không diễn đạt đúng completion composition**. Chọn:

~~~java
response.setStatusCode(HttpStatus.NO_CONTENT);
return response.setComplete();
~~~

### 14.7. Kết hợp manual write với typed return body

Không vừa `response.writeWith(...)` rồi trả `Mono<SomeDto>` từ cùng handler. Hai cơ chế có thể tranh commit/body; framework khó xử lý error/status nhất quán. Nếu muốn WebFlux tự encode JSON, trả Mono DTO hoặc ResponseEntity. Nếu muốn raw bytes, return Mono<Void> từ response writer.

### 14.8. Nghĩ rằng ResponseCookie tự tạo quyền truy cập

Một cookie value do client gửi có thể bị sửa hoặc giả mạo nếu không có signing/session infrastructure đúng. `HttpCookie`/`ResponseCookie` chỉ là HTTP cookie representation; application authorization phải dùng Spring Security và kiểm principal/resource ownership.

### 14.9. Tin hoàn toàn `X-Forwarded-For` hoặc `Forwarded`

Các headers này có thể do client tự đưa nếu proxy chưa loại bỏ. Cấu hình trusted ingress và forwarded-header transformer/strategy đúng; không tự xác định rate limit/authorization trên một IP dễ spoof từ header thô.

### 14.10. Log raw request body chứa credentials

JSON body có thể chứa password, OTP, address, card data hoặc tokens. Một WebFilter log body chung cho mọi route dễ rò rỉ thông tin qua log pipeline. Chỉ log metadata cần thiết, allowlist fields không nhạy cảm, giới hạn bytes và bảo vệ retention/access.

## 15. Buffering, streaming và backpressure

### 15.1. Reactive body không phải “một chunk = một tin nhắn”

Một `Flux<DataBuffer>` có thể phát nhiều buffers tùy Netty transport, TCP frames và producer tốc độ nào. Một dòng JSON có thể nằm trong nhiều buffers; một buffer có thể chứa nhiều dòng. Khi cần parse JSON streaming, dùng codec phù hợp, delimiter-aware parser hoặc protocol framing, không tự split theo sự kiện onNext.

### 15.2. Khi nào dùng aggregate?

Dùng aggregate khi:
- Payload nhỏ, có **maxByteCount**.
- Chỉ cần một DTO hoặc checksum trên toàn payload.
- Không thể xử lý streaming và memory budget chấp nhận được.
- Có error policy 413 rõ ràng.

Không aggregate khi:
- Upload nhiều MB/GB hoặc unknown size.
- Số requests đồng thời cao khiến memory N × payload lớn.
- Data cần stream tới file/object store hoặc downstream.
- Body chứa dữ liệu nhạy cảm không cần giữ toàn bộ trong heap.

### 15.3. Backpressure

`Flux<DataBuffer>` là Reactive Streams publisher, nên downstream có thể điều tiết demand; nhưng không nên suy ra mọi nguồn bên ngoài đều vô hạn sức chứa hoặc luôn có thể bị chậm lại mà không cần buffer. Khi output response chậm, Netty/codec và subscriber cancellation ảnh hưởng upstream. Mọi custom `flatMap`/`buffer`/`onBackpressureBuffer` cần giới hạn concurrency/bộ đệm rõ.

### 15.4. `writeAndFlushWith` và SSE

Với Server-Sent Events, điều quan trọng là event framing, flush cadence, heartbeat, error handling và client reconnect. Một custom `writeAndFlushWith` không tự xây SSE protocol. Spring WebFlux hỗ trợ `ServerSentEvent<T>` và content type `text/event-stream` ở cấp controller cao hơn; dùng nó khi phù hợp thay vì byte-level framing thủ công.

### 15.5. Response đã commit thì error body bị giới hạn

Nếu đã gửi status 200/headers và vài bytes, một exception sau đó thường không thể biến response thành JSON 500 chuẩn. Với streaming, có thể cần in-band error event, đóng connection hoặc retry protocol. Luôn suy nghĩ về **error trước commit** và **error sau commit** như hai trường hợp vận hành khác nhau.

## 16. Request/response trong lỗi và cancellation

### 16.1. Error trước khi request body giải mã xong

JSON malformed, header Content-Type sai hoặc body vượt codec limit có thể khiến decoder/handler phát error trước khi ứng dụng tạo response. Hệ thống WebFlux có `WebExceptionHandler` và `@ExceptionHandler`, nhưng không phải mọi lỗi HTTP đều bắt được bởi một advice duy nhất (đặc biệt security/proxy layer).

Khi trả lỗi:
- Giữ status có ý nghĩa (400/401/403/404/413/415/422/429/500...).
- Không phản chiếu raw body/SQL/internal stack traces.
- Không trả 200 với payload `{"error":"bad"}` nếu contract là HTTP error.
- Đảm bảo Cache-Control phù hợp khi body/status liên quan đến user.
- Kiểm integration tests qua filter chain và gateway thật.

### 16.2. Client disconnect

Nếu client đóng kết nối giữa chừng:
- Subscription có thể được cancel; behavior chính xác tùy server/adapter/timing.
- `doFinally` có thể thấy `SignalType.CANCEL` trong pipeline liên quan.
- Native/pooled buffers phải được giải phóng qua đúng operators.
- Business side effect đã commit trong DB không tự rollback.
- Không giả định server luôn gửi được body 500 khi client đã mất kết nối.

### 16.3. Timeout không giải quyết một blocking call

Nếu có `.timeout(Duration.ofSeconds(2))` trên request body hoặc downstream publisher, timeout phát onError/cancel. Nhưng blocking JDBC/client call không tôn trọng interruption có thể vẫn chạy. Tránh `block()` ở WebFilter, response preCommit callback và event-loop code. Với blocking legacy, dùng bounded worker và dependency-side timeouts.

## 17. Security và privacy khi làm việc với raw HTTP

### 17.1. Thông tin không đáng tin đến từ client

Các trường sau **không tự đủ để xác thực/ủy quyền**: `X-User`, `X-Tenant`, `X-Role`, `X-Forwarded-For`, `Cookie`, query parameter `?user`, URL segment `{tenant}`, hostname hoặc custom Origin.

Nếu hạ tầng có trusted identity proxy, cần bảo đảm proxy loại bỏ/rewrite spoofed identity headers, network path origin bị khóa và application xác thực signed/trusted identity theo contract. Không dùng `request.getHeaders().getFirst("X-Role")` để cấp ADMIN trực tiếp.

### 17.2. Bảo vệ cookie và token

- Cookie session: `Secure` trên HTTPS, `HttpOnly`, `SameSite` phù hợp.
- Bearer token: `Authorization` phải được redact ở logs/traces.
- Error response: không phản chiếu token trong `ProblemDetail.detail`.
- `Cache-Control: no-store` cho nội dung rất nhạy cảm, hoặc `private` nếu policy cho phép browser cache nhưng cấm shared cache.
- Không dùng `Vary: Cookie` để thay no-store/private cho body user-specific.
- Không gửi raw user details trong custom trace header.

### 17.3. CORS

Spring WebFlux có CORS infrastructure; `Origin` là request metadata và `Access-Control-Allow-Origin` là response header của browser policy. **CORS không phải cơ chế phân quyền user**. Không viết WebFilter tự echo bất kỳ `Origin` nào rồi bật credentials; dùng allowlist đúng, xử lý preflight và đảm bảo Spring Security reactive tích hợp phù hợp.

### 17.4. Header injection và response splitting

Không nối trực tiếp untrusted header/query values vào response headers, `Location` hoặc `Set-Cookie` mà không validate/encode. Runtime HTTP server thường kiểm những giá trị header không hợp lệ, nhưng không nên dựa toàn bộ an toàn vào parser. Nếu tạo redirect URL, dùng URI builder và allowlist destinations; tránh open redirects và CRLF injection.

## 18. Troubleshooting: lỗi và hướng kiểm

| Triệu chứng | Nguyên nhân phổ biến | Hướng khắc phục |
| --- | --- | --- |
| `@RequestBody` nhận body trống | WebFilter đã đọc `getBody()` | Không consume hai lần; decorator replay đúng |
| API upload gây tăng direct memory | DataBuffer pooled không release | Rà ownership/release/discard/cancel |
| `DataBufferLimitException` | Codec/join vượt max bytes | Giới hạn hợp lý, stream payload lớn, trả 413 theo policy |
| Controller không trả body dù set headers | Trả Mono chưa được subscribe/composed | Return `writeWith`/`setComplete` hoặc typed response |
| Header trong filter không xuất hiện | Đặt sau response commit | Dùng `beforeCommit` |
| `IllegalStateException` khi sửa response headers | Headers đã read-only/committed | Đặt sớm, kiểm beforeCommit |
| Response 204 vẫn có body | Ghi payload dù HTTP 204 | Chỉ `setComplete`, không body |
| POST JSON trả 415 | Content-Type không hợp route/decoder | Kiểm consumes và Content-Type |
| POST text/plain nhưng body parse sai | Nhầm charset hoặc manual decode từng chunk | Decode UTF-8 đúng qua codec/bound |
| GET query param trùng bị bỏ qua | Dùng `getFirst` | Xác định duplicate policy |
| Cookies bị log ra file | Log request headers/body không redact | Allowlist logging và secrets policy |
| Response cookie không được browser gửi lại | Domain/path/SameSite/Secure/TLS không phù hợp | Kiểm cookie attributes và browser behavior |
| Client IP toàn proxy | Đọc `getRemoteAddress` sau CDN | Trusted forwarded-header configuration |
| CPU thấp nhưng latency cao | Blocking I/O/event-loop starvation | Thread dump, không block, bounded pool |
| WebFilter đếm request nhiều lần? | Custom instrumentation không idempotent | Thiết kế per-request attribute và lifecycle rõ |
| Header CORS có nhưng browser vẫn chặn | Preflight/method/credentials mismatch | Kiểm OPTIONS và CORS policy |
| Advice không bắt 401 từ Security | Exception phát sinh trước handler | SecurityWebFilterChain handlers |
| Response đã stream mà handler muốn đổi 500 | Headers/body đã commit | Streaming-aware error protocol |
| Test WebTestClient đúng nhưng CDN sai | Cache/proxy có custom rules | End-to-end test qua CDN, kiểm Vary/Cache-Control |
| Một buffer có nửa ký tự UTF-8 | Decode từng chunk độc lập | Codec streaming/charset-aware decoder |
| Mono `block()` làm treo Netty loop | Blocking API trong reactive chain | Return/compose publishers; offload legacy calls |

### Quy trình gỡ lỗi thực dụng

1. Xác định app thực sự chạy **Spring WebFlux/Netty** hay MVC/Servlet: xem starters và runtime.
2. Xác định layer lỗi: gateway, WebFilter, handler mapping, decoder, controller, response writer, Security hay client.
3. Ghi method, path, Content-Type, Accept, status, request ID/trace ID; **không log raw credentials**.
4. Kiểm có code nào subscribe request body ngoài pipeline hay không.
5. Kiểm DataBufferUtils.join/collectList có max size và release trên success/error/cancel không.
6. Nếu response header mất, xác minh set trước commit hay trong beforeCommit.
7. Kiểm response đã ghi qua typed return hay manual `writeWith`/`setComplete`, không trộn.
8. Với status bất ngờ, kiểm Spring Security/WebExceptionHandler/filter order.
9. Với client IP/redirect URL sai, kiểm trusted forwarded headers và proxy rewrite.
10. Dùng WebTestClient integration test trên embedded server, sau đó test gateway/CDN/browser thật nếu sản phẩm có các tầng đó.

## 19. Checklist khi viết WebFlux HTTP infrastructure

- [ ] Import đúng `org.springframework.http.server.reactive.ServerHttpRequest/Response`.
- [ ] Dùng `ServerWebExchange` cho request + response + attributes của một interaction.
- [ ] Không coi query/headers/cookies là identity đã xác thực.
- [ ] Không tự parse URI bằng string splitting hoặc tin mọi forwarded headers.
- [ ] Không đọc raw body trong nhiều filter/controller cùng lúc.
- [ ] Dùng `@RequestBody Mono<T>`/codecs cho JSON khi không cần xử lý raw bytes.
- [ ] Khi aggregate DataBuffer, đặt max bytes; release joined buffers sau khi copy/consume.
- [ ] Không release buffers đã chuyển quyền sở hữu cho response writer.
- [ ] Không ghi raw body/tokens/PII vào logs.
- [ ] Set status/headers/cookies trước response commit; `beforeCommit` callback lazy/nhẹ.
- [ ] Return Mono<Void> từ `writeWith`/`setComplete`; không subscribe/block thủ công.
- [ ] Không vừa manual write vừa trả thêm body từ annotated controller.
- [ ] Phân biệt response lỗi trước/sau khi headers commit.
- [ ] Chặn uploads quá lớn tại gateway/server/application.
- [ ] Cấu hình CORS, Spring Security reactive, cookie và cache privacy riêng.
- [ ] Giới hạn memory/concurrency, đo cancellation/timeout và reference leaks.
- [ ] Test metadata/query/headers/cookies, JSON, 204, 201, 413 và error behavior.
- [ ] Với streaming/file upload, dùng protocol/codec chuyên dụng thay aggregate mù.
- [ ] Xác nhận headers cuối sau WebFilter/security/proxy, không chỉ controller code.

### Câu hỏi tự kiểm tra

**1.** `ServerHttpRequest` và `ServerHttpResponse` thuộc package nào?

**Trả lời:** `org.springframework.http.server.reactive`, không phải Servlet `HttpServletRequest`/`HttpServletResponse`.

**2.** Vì sao `request.getBody().next()` không phải cách đọc JSON hoàn chỉnh?

**Trả lời:** Nó lấy phần tử DataBuffer đầu tiên, body có thể gồm nhiều buffers không trùng JSON boundaries.

**3.** Có thể đọc request body ở WebFilter rồi để controller đọc lại như thường không?

**Trả lời:** Không bảo đảm. Raw body thường single-consumer streaming; cần decorator/replay được thiết kế nếu có lý do đặc biệt, hoặc không consume trong filter.

**4.** Khi tự đọc joined pooled DataBuffer rồi chuyển sang byte array, phải làm gì?

**Trả lời:** Copy bytes, bảo đảm `DataBufferUtils.release` trong `finally`; xử lý cả giới hạn size và error/cancel.

**5.** `response.beforeCommit(...)` khác `chain.filter(exchange).then(...)` ở điểm nào?

**Trả lời:** beforeCommit callback chạy ngay trước commit; `then` sau chain có thể quá trễ để thay response headers.

**6.** Vì sao `writeWith(...)` trả Mono<Void>?

**Trả lời:** Ghi body là hoạt động reactive có completion/error; phải return/compose Mono để framework subscribe đúng vòng đời, không tự block.

**7.** Khi trả `Mono<DTO>` có nhất thiết gọi `ServerHttpResponse.writeWith` thủ công không?

**Trả lời:** Không. Spring WebFlux codecs có thể encode DTO; chỉ dùng raw write khi cần kiểm soát bytes/streaming thấp hơn.

**8.** `HttpCookie` và `ResponseCookie` khác gì?

**Trả lời:** HttpCookie là cookie đọc từ request; ResponseCookie tạo cookie server gửi qua Set-Cookie với thuộc tính như Path, HttpOnly, SameSite, Secure.

**9.** `exchange.getAttributes()` có phải session không?

**Trả lời:** Không. Attributes thuộc request/response interaction; WebSession có lifecycle riêng và được lấy qua `getSession()`.

**10.** `X-Forwarded-For` có thể dùng trực tiếp làm client IP đáng tin không?

**Trả lời:** Không nếu không có trusted proxy configuration; attacker có thể spoof header.

**11.** Vì sao không đổi HTTP status từ 200 sang 500 sau khi đã stream bytes?

**Trả lời:** Response đã commit headers/status và có thể đã gửi body; cần error handling phù hợp streaming và không hứa sửa status sau commit.

## 20. Tài liệu chính thức

- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux.html): mô hình WebFlux, HTTP server adapters, handler infrastructure.
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): HandlerMapping, HandlerAdapter, HandlerResultHandler.
- [Spring Framework — WebFlux Method Arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html): `ServerHttpRequest`, `ServerHttpResponse` và `ServerWebExchange` trong annotated controllers.
- [Spring Framework — ServerHttpRequest 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html): request method/URI/headers/cookies/body APIs.
- [Spring Framework — ServerHttpResponse 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html): status, cookies, headers, response writing, commit.
- [Spring Framework — ServerWebExchange 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/ServerWebExchange.html): request/response interaction, session, attributes, mutator.
- [Spring Framework — WebFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebFilter.html): reactive middleware contract.
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): DataBufferFactory, pooled buffers, release, join và codecs.
- [Spring Framework — DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): bounded join, retain/release và stream utilities.
- [Spring Framework — ReactiveHttpOutputMessage Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/ReactiveHttpOutputMessage.html): `beforeCommit`, `isCommitted`, `writeWith`, `writeAndFlushWith`, `setComplete`.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): reactive HTTP integration testing.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): dependency/runtime server và configuration.
- [Spring Framework — CORS for WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): browser cross-origin và reactive security integration.
- [Spring Security — WebFlux](https://docs.spring.io/spring-security/reference/reactive/index.html): reactive SecurityWebFilterChain và context.

**Ghi nhớ:** `ServerHttpRequest` cung cấp metadata và body đầu vào dạng `Flux<DataBuffer>`; `ServerHttpResponse` là nơi xây status/headers/cookies và ghi output reactive. `ServerWebExchange` nối chúng với lifecycle của một HTTP request. Hãy ưu tiên Spring codecs/DTOs khi có thể, tránh consume body nhiều lần, kiểm buffer ownership, đặt giới hạn kích thước và quyết định headers trước commit. Khi cần raw HTTP infrastructure, hãy test trên WebFlux/Netty thực thay vì chỉ tin một phương thức trả về `Mono`.

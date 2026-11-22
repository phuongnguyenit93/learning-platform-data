# before, after, filter và HandlerFilterFunction trong Spring WebFlux

## 1. Bối cảnh: xử lý chung quanh một functional endpoint

Spring WebFlux cung cấp mô hình endpoint hàm **WebFlux.fn** bên cạnh controller annotation. Trong mô hình này, một request được định tuyến đến một hàm xử lý, rồi handler tạo response reactive.

Ba thành phần nền tảng:

- **ServerRequest**: đại diện HTTP request, cho phép đọc method, path, headers, query parameters, principal và body.
- **HandlerFunction<ServerResponse>**: nhận ServerRequest và trả về `Mono<ServerResponse>`.
- **RouterFunction<ServerResponse>**: chọn HandlerFunction phù hợp với request; nếu không có route phù hợp, nó trả về `Mono.empty()`.

Một handler tối giản:

~~~java
HandlerFunction<ServerResponse> hello = request ->
        ServerResponse.ok().bodyValue("Hello WebFlux");
~~~

Một route:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
        .GET("/hello", hello)
        .build();
~~~

Khi ứng dụng có nhiều endpoint, thường phát sinh các công việc lặp lại:

- Gắn correlation/request ID vào request.
- Ghi log request và status response.
- Kiểm tra API key hoặc quyền truy cập.
- Thêm response header.
- Ghi metric và thời gian xử lý.
- Chuẩn hóa một số lỗi thành HTTP response.
- Áp dụng một chính sách cho một nhóm route thay vì lặp trong từng handler.

**before, after và filter** cho phép đặt những công việc này ở quanh handler. Chúng thuộc API **RouterFunction.Builder** của WebFlux.fn. **HandlerFilterFunction** là kiểu hàm lọc tổng quát đứng sau phương thức `filter(...)`.

## 2. Phân biệt ba phương thức

| Phương thức | Đầu vào | Đầu ra | Công việc phù hợp |
| --- | --- | --- | --- |
| `before(...)` | `ServerRequest` | `ServerRequest` | Biến đổi request đồng bộ trước handler |
| `after(...)` | `ServerRequest` và response của handler | Response | Quan sát hoặc biến đổi response đồng bộ sau handler |
| `filter(...)` | `ServerRequest` và handler kế tiếp | `Mono<ServerResponse>` | Bao quanh handler, có thể cho chạy tiếp, chặn hoặc xử lý reactive |

Luồng khái niệm:

~~~text
HTTP request
     |
     v
  before(request)
     |
     v
 HandlerFilterFunction
     |
     +---- kiểm tra / short-circuit
     |
     v
 HandlerFunction
     |
     v
  after(request, response)
     |
     v
 HTTP response
~~~

Sơ đồ mô tả luồng thành công cơ bản. Với `filter`, có thể có nhiều filter lồng nhau; filter bên ngoài gọi filter tiếp theo thông qua `next.handle(request)`. Nếu một filter không gọi `next` mà tự trả response, các bước phía sau trong chain không chạy.

### 2.1. before: xử lý request trước handler

Chữ ký khái niệm:

~~~java
Builder before(Function<ServerRequest, ServerRequest> requestProcessor);
~~~

`before` nhận một hàm đồng bộ, đọc request hiện tại và trả về request mà handler sẽ nhận. Ví dụ thêm header nội bộ:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/hello", request ->
        ServerResponse.ok().bodyValue(
            request.headers().firstHeader("X-Request-Source")))
    .before(request -> ServerRequest.from(request)
        .header("X-Request-Source", "router-before")
        .build())
    .build();
~~~

Khi gọi `GET /hello`, handler đọc được header `X-Request-Source: router-before`.

`ServerRequest` có contract bất biến. Vì vậy, khi muốn tạo request mới với header thay đổi, dùng `ServerRequest.from(request)` để tạo builder, rồi gọi `build()`. Không sửa trực tiếp object request ban đầu.

Các ứng dụng thường dùng `before` để:

- Chuẩn hóa hoặc bổ sung request metadata.
- Thêm attribute để handler đọc.
- Ghi log thông tin request không nhạy cảm.
- Chuẩn hóa một số header theo hợp đồng nội bộ.
- Chuẩn bị dữ liệu đồng bộ đã có sẵn trước khi handler chạy.

**Giới hạn quan trọng:** `before` là `Function<ServerRequest, ServerRequest>` đồng bộ. Nó không trả `Mono`, nên không phù hợp với việc phải gọi database, HTTP service hoặc xác minh token bất đồng bộ. Dùng `HandlerFilterFunction` cho công việc đó.

### 2.2. after: xử lý response sau handler

Chữ ký khái niệm:

~~~java
Builder after(
    BiFunction<ServerRequest, ServerResponse, ServerResponse> responseProcessor);
~~~

`after` nhận request ban đầu đã đi qua các bước xử lý trước đó và response do handler tạo ra. Ví dụ log status:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/hello", request ->
        ServerResponse.ok().bodyValue("Hello"))
    .after((request, response) -> {
        System.out.println(
            request.method() + " " + request.path()
                + " -> " + response.statusCode());
        return response;
    })
    .build();
~~~

Handler vẫn trả response như cũ. `after` chỉ quan sát status và trả lại response.

Nếu handler cần thêm header, hãy tạo header cùng với response **trước khi** viết body. `after` dùng callback đồng bộ, không trả `Mono<ServerResponse>`:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/hello", request ->
        ServerResponse.ok()
            .header("X-Response-Stage", "handler")
            .bodyValue("Hello"))
    .after((request, response) -> {
        System.out.println("Response status: " + response.statusCode());
        return response;
    })
    .build();
~~~

Nếu muốn thêm header **trên toàn bộ HTTP response**, đặt một `WebFilter` để thao tác `ServerWebExchange.getResponse().getHeaders()` trước khi response commit. `ServerResponse.from(response)` chỉ sao chép status và header, **không tự sao chép body**; gọi `build()` với builder đó không giữ nguyên body của response cũ. `HandlerFilterFunction.ofResponseProcessor` thích hợp để xử lý response dưới dạng `Mono` nhưng không tự giải quyết việc copy body.

`after` chỉ nhận được một response khi handler chain hoàn tất bằng response bình thường. Nếu handler phát lỗi thay vì tạo response, không có response để callback `after` xử lý. Muốn quan sát lỗi, dùng `filter` với `doOnError`/`onErrorResume` hoặc cấu hình error handling ở tầng phù hợp.

### 2.3. filter: bao quanh handler

`filter(...)` nhận một `HandlerFilterFunction`. Đây là functional interface với hai tham số:

- `ServerRequest request`: request đã đi qua các bước trước đó.
- `HandlerFunction<T> next`: handler hoặc filter kế tiếp trong chain.

Chữ ký cốt lõi:

~~~java
Mono<R> filter(
    ServerRequest request,
    HandlerFunction<T> next);
~~~

`T` và `R` là kiểu response; trong hầu hết ứng dụng cả hai đều là `ServerResponse`.

Ví dụ chặn request thiếu API key:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> apiKeyFilter =
    (request, next) -> {
        String apiKey = request.headers().firstHeader("X-Api-Key");

        if ("demo-secret".equals(apiKey)) {
            return next.handle(request);
        }

        return ServerResponse.status(HttpStatus.UNAUTHORIZED)
            .header(HttpHeaders.WWW_AUTHENTICATE, "ApiKey")
            .bodyValue("unauthorized");
    };
~~~

Gắn filter vào router:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/private", request ->
        ServerResponse.ok().bodyValue("private-data"))
    .filter(apiKeyFilter)
    .build();
~~~

Kết quả:

- Request có `X-Api-Key: demo-secret`: filter gọi `next.handle(request)`; handler thực thi và trả response.
- Request thiếu hoặc sai API key: filter tự trả HTTP 401; handler không chạy.

**`next.handle(request)` là điểm tiếp tục chain.** Việc gọi nó là tùy chọn. Nếu không gọi, filter có thể kết thúc sớm bằng response riêng, ví dụ 401, 403 hoặc response từ cache.

`filter` mạnh hơn `before` và `after` vì nó có thể làm việc reactive: gọi một service xác thực, chờ một `Mono<Boolean>`, rồi mới quyết định gọi handler.

## 3. HandlerFilterFunction là gì?

`HandlerFilterFunction<T extends ServerResponse, R extends ServerResponse>` đại diện một hàm lọc handler. Nó cho phép viết lambda hoặc method reference và tái sử dụng cùng một chính sách cho nhiều router.

Các API đáng chú ý:

| API | Ý nghĩa |
| --- | --- |
| `filter(request, next)` | Áp dụng filter vào handler tiếp theo |
| `apply(handler)` | Bọc một HandlerFunction thành HandlerFunction đã lọc |
| `andThen(after)` | Kết hợp filter hiện tại với filter tiếp theo; filter hiện tại chạy trước |
| `ofRequestProcessor(...)` | Chuyển một request processor trả Mono<ServerRequest> thành filter |
| `ofResponseProcessor(...)` | Chuyển một response processor trả Mono<R> thành filter |

### 3.1. Filter dạng lambda

Đây là cách trực tiếp nhất:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> logFilter =
    (request, next) -> {
        System.out.println("before: " + request.path());

        return next.handle(request)
            .doOnNext(response ->
                System.out.println(
                    "after: " + response.statusCode()));
    };
~~~

Ví dụ này ghi log trước khi handler được gọi và khi response phát ra. `doOnNext` chỉ quan sát tín hiệu response; nó không thay đổi status hoặc body.

Nếu cần đo thời gian, dùng `Mono.defer` để bắt đầu đo khi subscription thực sự chạy:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> timingFilter =
    (request, next) -> Mono.defer(() -> {
        long start = System.nanoTime();

        return next.handle(request)
            .doFinally(signal -> {
                long elapsed = System.nanoTime() - start;
                System.out.println(
                    request.path() + " completed in " + elapsed + " ns");
            });
    });
~~~

`doFinally` được gọi khi chain kết thúc bằng complete, error hoặc cancel. Đoạn này là ví dụ instrumentation; không log từng request với dữ liệu nhạy cảm hoặc độ chi tiết quá lớn nếu hệ thống có lưu lượng cao.

### 3.2. ofRequestProcessor

`HandlerFilterFunction.ofRequestProcessor(...)` thích hợp khi logic chỉ cần biến đổi request bằng một hàm trả `Mono<ServerRequest>`.

Chữ ký:

~~~java
static HandlerFilterFunction<?, ?> ofRequestProcessor(
    Function<ServerRequest, Mono<ServerRequest>> requestProcessor);
~~~

Ví dụ processor:

~~~java
Function<ServerRequest, Mono<ServerRequest>> addHeader =
    request -> Mono.just(
        ServerRequest.from(request)
            .header("X-Processed-By", "request-processor")
            .build());
~~~

Nó biểu diễn một request transformation reactive. Nếu việc chuẩn bị request cần I/O bất đồng bộ, có thể trả Publisher tương ứng từ processor thay vì thực hiện blocking trong callback.

Vì factory trả kiểu generic wildcard, khi đưa vào một biến có kiểu response cụ thể, cần để Java suy luận tại điểm sử dụng phù hợp hoặc chuyển đổi kiểu một cách tường minh. Trong nhiều trường hợp, một lambda `(request, next) -> processor.apply(request).flatMap(next::handle)` dễ đọc và rõ generic type hơn.

### 3.3. ofResponseProcessor

`ofResponseProcessor` thích hợp khi chỉ cần biến đổi response bằng một hàm trả `Mono<R>`.

Chữ ký:

~~~java
static <T extends ServerResponse, R extends ServerResponse>
HandlerFilterFunction<T, R> ofResponseProcessor(
    Function<T, Mono<R>> responseProcessor);
~~~

Ví dụ quan sát response một cách reactive **mà không dựng lại/mất body** (snippet cần import `reactor.core.publisher.Mono`):

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> auditResponse =
    HandlerFilterFunction.ofResponseProcessor(response ->
        Mono.just(response)
            .doOnNext(res ->
                System.out.println("status=" + res.statusCode())));
~~~

Gắn vào router:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/hello", request ->
        ServerResponse.ok().bodyValue("Hello"))
    .filter(auditResponse)
    .build();
~~~

`ofResponseProcessor` nhận processor trả `Mono<ServerResponse>` nên có thể làm công việc bất đồng bộ, ghi metric hoặc xử lý lỗi phù hợp; ở đây trả lại **chính response ban đầu** để bảo toàn body. Nếu cần thêm header cho mọi response mà không phải dựng lại body, dùng `WebFilter` ở tầng exchange; không chỉ `ServerResponse.from(response).header(...).build()`.

### 3.4. Kết hợp nhiều HandlerFilterFunction

`andThen` tạo một filter kết hợp. JavaDoc định nghĩa thứ tự: **filter hiện tại chạy trước, sau đó mới đến filter truyền vào andThen**.

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> first =
    (request, next) -> {
        System.out.println("filter-1");
        return next.handle(request);
    };

HandlerFilterFunction<ServerResponse, ServerResponse> second =
    (request, next) -> {
        System.out.println("filter-2");
        return next.handle(request);
    };

HandlerFilterFunction<ServerResponse, ServerResponse> combined =
    first.andThen(second);
~~~

`combined` có thể gắn vào router bằng `.filter(combined)`. Với các filter trước/sau handler, hãy viết test để xác nhận thứ tự thực thi và tránh dựa vào một giả định không được kiểm chứng khi chain có nhiều lớp lồng nhau.

## 4. Phạm vi filter: top-level và nested routes

Một điểm quan trọng trong WebFlux.fn là **filter chỉ áp dụng cho các route được xây dựng trong phạm vi RouterFunction.Builder tương ứng**.

Ví dụ:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .path("/people", people -> people
        .GET("/{id}", handler::getPerson)
        .GET(handler::listPeople)
        .before(request -> ServerRequest.from(request)
            .header("X-Group", "people")
            .build()))
    .GET("/health", handler::health)
    .after((request, response) -> {
        logResponse(response);
        return response;
    })
    .build();
~~~

Trong ví dụ:

- `before` nằm bên trong builder của `/people` nên chỉ áp dụng cho hai route GET thuộc nhóm đó.
- `after` nằm ở builder bên ngoài nên áp dụng cho các route được tạo bởi builder bên ngoài, bao gồm route nested.
- `/health` là top-level route; nó không nhận header `X-Group`.
- `after` vẫn quan sát response của `/health` và các route nested.

Mô hình:

~~~text
Builder ngoài
  |
  +-- path("/people")
  |      |
  |      +-- GET /people/{id}
  |      +-- GET /people
  |      +-- before: X-Group=people
  |
  +-- GET /health
  |
  +-- after: log response cho các route của builder ngoài
  +-- build()
~~~

Nếu thêm `filter` vào builder nested, filter đó chỉ áp dụng cho các route thuộc nested builder. Nếu thêm `filter` ở builder ngoài, nó áp dụng cho tất cả route được tạo bởi builder ngoài.

Đây là lý do nên nhóm route theo phạm vi nghiệp vụ hoặc chính sách chung:

- `/admin/**`: yêu cầu authorization quản trị.
- `/internal/**`: thêm trace metadata hoặc kiểm tra network policy.
- `/public/**`: có chính sách cache/headers riêng.
- Top-level `/health`: có thể không cần các filter nghiệp vụ.

Không đặt một filter nhạy cảm vào builder quá rộng nếu có route public hoặc health endpoint nằm trong cùng phạm vi.

## 5. Thứ tự route và thứ tự filter là hai chuyện khác nhau

**RouterFunction** đánh giá các route theo thứ tự kết hợp. Route đầu tiên match được dùng; nếu không match, route tiếp theo được thử. Vì vậy, route cụ thể nên được khai báo trước route tổng quát.

Ví dụ:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/users/me", handler::currentUser)
    .GET("/users/{id}", handler::userById)
    .GET("/users/**", handler::fallback)
    .build();
~~~

`/users/me` nên đứng trước `/users/{id}` và catch-all. Cơ chế này khác annotation controller, nơi Spring dùng comparator để chọn mapping cụ thể hơn.

Filter order là thứ tự bao quanh handler. Có thể hình dung:

~~~text
Filter A enters
    Filter B enters
        Handler runs
    Filter B receives response
Filter A receives response
~~~

Khi filter A gọi `next.handle(request)`, nó chuyển điều khiển sang phần kế tiếp. Khi Publisher trả response, các bước xử lý sau của filter chạy theo chiều ngược lại.

Với `HandlerFilterFunction.andThen`, thứ tự được định nghĩa rõ: filter hiện tại trước, filter sau tiếp theo. Với builder có nhiều filter và nested builder, hãy kiểm tra phạm vi và thứ tự bằng integration test thay vì suy ra từ vị trí text trong một file.

## 6. Chọn before, after hay filter?

| Yêu cầu | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Thêm header/attribute đồng bộ vào request | `before` | Một hàm request → request là đủ |
| Log method/path trước handler | `before` | Chỉ cần quan sát request |
| Log status sau response | `after` | Có cả request và response |
| Thêm response header bằng xử lý đồng bộ | Có thể dùng `after` nếu có cách tạo response đồng bộ; thường dùng filter khi cần builder reactive | `after` không nhận Mono |
| Xác thực token qua service reactive | `filter` | Có thể chờ Mono trước khi gọi handler |
| Chặn request và trả 401/403 | `filter` | Không cần gọi next |
| Xử lý lỗi từ handler thành fallback response | `filter` với onErrorResume hoặc builder `onError` | Có thể quan sát tín hiệu lỗi |
| Thêm response header bằng ServerResponse builder | `ofResponseProcessor` | Response builder trả Mono |
| Đo cả complete, error và cancel | `filter` với `doFinally` | Bao quanh lifecycle của Publisher |
| CORS cho toàn WebFlux app | `CorsWebFilter` hoặc cấu hình CORS WebFlux | CORS là concern ở tầng web filter |
| Security cho toàn bộ ứng dụng | Spring Security/WebFilter chain | Phạm vi bảo vệ rộng hơn router chức năng |

Quy tắc thực hành:

- Dùng **before** cho request transformation đơn giản và đồng bộ.
- Dùng **after** cho response observation/transform đồng bộ.
- Dùng **HandlerFilterFunction** khi cần điều khiển chain, xử lý bất đồng bộ hoặc thay response.
- Dùng **WebFilter** khi chính sách phải áp dụng xuyên suốt WebFlux application, không chỉ các functional routes.

## 7. Xử lý bất đồng bộ trong HandlerFilterFunction

Một filter có thể gọi service reactive để quyết định có cho request đi tiếp:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> authorizationFilter =
    (request, next) -> request.principal()
        .flatMap(principal ->
            authorizationService.canAccess(principal, request.path()))
        .flatMap(allowed -> {
            if (allowed) {
                return next.handle(request);
            }
            return ServerResponse.status(HttpStatus.FORBIDDEN).build();
        });
~~~

Đây là **đoạn minh họa**, giả định có `authorizationService.canAccess(...)` trả `Mono<Boolean>`. Filter đọc principal từ request, kiểm tra quyền bất đồng bộ, rồi:

- `true`: gọi handler tiếp theo.
- `false`: trả 403.
- Lỗi từ authorization service: lỗi đi xuống chain, trừ khi filter có xử lý lỗi riêng.

Không dùng `block()` để chờ kết quả authorization. Việc block có thể chặn event-loop và phá vỡ lợi ích non-blocking của WebFlux.

Không gọi `subscribe()` thủ công trong filter. Hãy trả Publisher cho chain để Reactor quản lý cancellation, error, completion và backpressure.

### 7.1. 401 và 403

- **401 Unauthorized**: request chưa được xác thực hoặc credentials không hợp lệ; hệ thống thường cần challenge phù hợp trong `WWW-Authenticate`.
- **403 Forbidden**: đã biết danh tính hoặc không có quyền thực hiện thao tác.

Một filter minh họa không thay thế đầy đủ Spring Security. Trong production, dùng authentication/authorization chain chuẩn, không chỉ so sánh một header tự do với chuỗi bí mật cố định.

### 7.2. Filter có thể short-circuit

Ví dụ cache:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> cacheFilter =
    (request, next) -> cache.find(request.path())
        .flatMap(cached -> ServerResponse.ok().bodyValue(cached))
        .switchIfEmpty(Mono.defer(() -> next.handle(request)));
~~~

Đây là ví dụ minh họa; giả định `cache.find(path)` trả `Mono<String>`. Nếu cache có dữ liệu, handler không chạy. Nếu cache rỗng, filter gọi handler.

Trong thực tế cần cân nhắc cache key theo query, user/tenant, Accept header và authorization. Không trả cache dùng chung cho người dùng khác nhau chỉ vì URL giống nhau.

## 8. Xử lý lỗi trong filter và RouterFunctions.Builder

`after` nhận response thành công; nó không phải nơi phù hợp để chuyển exception thành HTTP error response. Có một số lựa chọn:

### 8.1. Dùng onErrorResume trong HandlerFilterFunction

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> errorFilter =
    (request, next) -> next.handle(request)
        .onErrorResume(IllegalArgumentException.class, error ->
            ServerResponse.badRequest()
                .bodyValue("invalid request"));
~~~

Nếu handler phát `IllegalArgumentException`, filter thay lỗi đó bằng HTTP 400. Lỗi loại khác tiếp tục phát ra.

### 8.2. Dùng onError trên RouterFunctions.Builder

Builder cũng có overload `onError` theo exception class hoặc predicate:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
    .GET("/items/{id}", handler::getItem)
    .onError(IllegalArgumentException.class,
        (error, request) ->
            ServerResponse.badRequest().build())
    .build();
~~~

Cơ chế này gắn error-to-response policy vào router builder. Chọn một phạm vi đủ hẹp và không chuyển mọi lỗi hệ thống thành 400.

### 8.3. Khi cần xử lý lỗi toàn ứng dụng

Nếu exception có thể phát sinh từ nhiều route, annotation controller hoặc WebFlux infrastructure, hãy dùng cơ chế error handling toàn ứng dụng như `WebExceptionHandler`, Spring Security hoặc cấu hình phù hợp. Không lặp cùng một chính sách ở nhiều filter nếu có thể xử lý ở một boundary chung.

Không để lỗi nội bộ, stack trace hoặc thông tin xác thực trong response body. Ghi log với correlation ID và trả một error representation an toàn.

## 9. Phân biệt HandlerFilterFunction và WebFilter

Hai API có tên gần nhau nhưng phạm vi khác:

| Tiêu chí | HandlerFilterFunction | WebFilter |
| --- | --- | --- |
| Thuộc tầng | WebFlux.fn / RouterFunction | WebFlux WebHandler chain |
| Phạm vi | Những route được gắn vào RouterFunction/builder | Toàn bộ request đi qua WebFlux filter chain |
| Kiểu hàm | `ServerRequest` + next `HandlerFunction` → `Mono<ServerResponse>` | `ServerWebExchange` + next `WebFilterChain` → `Mono<Void>` |
| Phù hợp | Filter theo route, nhóm functional endpoint, response dạng ServerResponse | Security, CORS, tracing, request-wide policy |
| Áp dụng cho annotated controller? | Không tự động | Có, nếu request đi qua WebFlux chain |

Ví dụ WebFilter:

~~~java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
class RequestIdWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = exchange.getRequest()
            .getHeaders()
            .getFirst("X-Request-Id");

        if (requestId == null || requestId.isBlank()) {
            requestId = UUID.randomUUID().toString();
        }

        exchange.getResponse().getHeaders()
            .set("X-Request-Id", requestId);

        return chain.filter(exchange);
    }
}
~~~

Đây là **mã minh họa** cần import `WebFilter`, `WebFilterChain`, `ServerWebExchange`, `Mono`, `Component`, `Order`, `Ordered` và `UUID`. WebFilter can thiệp ở mức WebExchange và áp dụng trên các request đi qua WebFlux, bao gồm functional endpoints và annotated controllers.

**Không đăng ký cùng một chính sách vừa là WebFilter toàn cục vừa là HandlerFilterFunction theo route** nếu không cần. Có thể khiến log, auth hoặc response header chạy hai lần.

### CORS

Spring WebFlux cung cấp `CorsWebFilter` riêng cho CORS của functional endpoints. Không nên tự viết một filter nhỏ chỉ để thêm `Access-Control-Allow-Origin` mà bỏ qua preflight, credentials, allowed headers và policy của Spring Security. CORS là một policy ở boundary web, nên cấu hình bằng cơ chế CORS chuẩn.

## 10. Những điểm cần cẩn thận với request body và response body

### 10.1. Request body là stream

Trong WebFlux, body của request được biểu diễn bằng Publisher như `Mono` hoặc `Flux`. Filter không nên tùy tiện đọc body chỉ để log rồi tiếp tục gọi handler, vì việc đọc có thể tiêu thụ stream. Nếu cần kiểm tra payload, phải thiết kế việc cache/replay hoặc dùng cơ chế đọc phù hợp với body và giới hạn kích thước.

Tránh:

~~~java
// Anti-pattern minh họa: đọc body để log rồi mong handler tự đọc lại.
request.bodyToMono(String.class)
    .doOnNext(System.out::println)
    .then(next.handle(request));
~~~

Đoạn trên không tự tái tạo request body cho handler. Handler có thể không còn đọc được dữ liệu theo cách dự kiến.

Nếu thật sự cần inspect body, dùng giải pháp rõ ràng để buffer/rebuild request, đặt giới hạn byte và cân nhắc dữ liệu nhạy cảm. Không log password, access token hoặc thông tin cá nhân.

### 10.2. Response body cũng có thể là stream

Một response có thể chứa `Flux<DataBuffer>` hoặc Publisher dữ liệu lớn. Filter response thông thường nên sửa status/header/metadata; không nên subscribe hoặc đọc body để log vì sẽ tiêu thụ stream hoặc làm thay đổi backpressure.

Nếu cần ghi log nội dung response, cần một chiến lược decorator/buffering có giới hạn và phải cân nhắc memory, streaming, cancellation, latency và privacy.

## 11. Chương trình Spring Boot WebFlux Java 17+ hoàn chỉnh

Ví dụ dưới đây tạo ba route:

- `GET /api/hello`: `before` thêm request header để handler đọc.
- `GET /api/private`: nested `HandlerFilterFunction` kiểm tra API key và có thể chặn.
- `GET /public`: route top-level không nhận request header chỉ áp dụng trong nhóm `/api`.
- `after` ở builder ngoài log response cho các route thuộc builder.
- Một response filter thêm header `X-Response-Filter` cho các route được builder ngoài tạo.

Yêu cầu: **Java 17+**, **Maven 3.6.3+** và Spring Boot 4.1.2. Hãy dùng patch release được tổ chức hỗ trợ trong dự án thực tế; Boot BOM quản lý Spring Framework và Reactor.

### 11.1. Cấu trúc dự án

~~~text
functional-filter-demo/
  pom.xml
  src/main/java/example/filterdemo/FilterDemoApplication.java
  src/main/java/example/filterdemo/FunctionalRoutes.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>functional-filter-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
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

### 11.3. Class khởi động

**src/main/java/example/filterdemo/FilterDemoApplication.java**

~~~java
package example.filterdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }
}
~~~

### 11.4. Router và các filter

**src/main/java/example/filterdemo/FunctionalRoutes.java**

~~~java
package example.filterdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.server.HandlerFilterFunction;
import org.springframework.web.reactive.function.server.HandlerFunction;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.WebFilter;

@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> routes() {

        HandlerFunction<ServerResponse> hello = request -> {
            String source = request.headers()
                    .firstHeader("X-Request-Source");

            return ServerResponse.ok()
                    .bodyValue("hello; source=" + source);
        };

        HandlerFunction<ServerResponse> privateData = request ->
                ServerResponse.ok().bodyValue("private-data");

        HandlerFilterFunction<ServerResponse, ServerResponse> apiKeyFilter =
                (request, next) -> {
                    String key = request.headers()
                            .firstHeader("X-Api-Key");

                    if ("demo-secret".equals(key)) {
                        return next.handle(request);
                    }

                    return ServerResponse.status(HttpStatus.UNAUTHORIZED)
                            .header(HttpHeaders.WWW_AUTHENTICATE, "ApiKey")
                            .bodyValue("unauthorized");
                };

        return RouterFunctions.route()
                .path("/api", api -> api
                        .GET("/hello", hello)
                        .path("/private", privateRoute -> privateRoute
                                .GET(privateData)
                                .filter(apiKeyFilter))
                        .before(request -> ServerRequest.from(request)
                                .header("X-Request-Source", "router-before")
                                .build())
                )
                .GET("/public", request ->
                        ServerResponse.ok().bodyValue("public"))
                .after((request, response) -> {
                    System.out.println(
                            request.method() + " " + request.path()
                                    + " -> " + response.statusCode());
                    return response;
                })
                .build();
    }

    @Bean
    WebFilter responseHeaderFilter() {
        return (exchange, chain) -> {
            exchange.getResponse().getHeaders()
                    .set("X-Response-Filter", "applied");
            return chain.filter(exchange);
        };
    }
}
~~~

**Giải thích phạm vi:**

- `before` nằm trong builder `/api` nên `/api/hello` và `/api/private` nhận `X-Request-Source`.
- Filter `apiKeyFilter` nằm trong builder `/private` nên chỉ bảo vệ route `/api/private`.
- `after` nằm ở builder ngoài, nên log cả các response của route nested và `/public`.
- Bean `responseHeaderFilter` là `WebFilter` ở tầng HTTP exchange, áp dụng cho `/api` và `/public`, đặt header trước khi response commit mà **không thay body**.
- `/public` không có `X-Request-Source` vì nó nằm ngoài builder `/api`.

### 11.5. Chạy ứng dụng

Trong thư mục có `pom.xml`:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

Ứng dụng mặc định chạy tại port 8080.

**Request 1 — before đã thêm header:**

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Body dự kiến:

~~~text
hello; source=router-before
~~~

Response có header:

~~~text
X-Response-Filter: applied
~~~

**Request 2 — thiếu API key, filter chặn:**

~~~bash
curl -i http://localhost:8080/api/private
~~~

Kết quả dự kiến:

~~~text
HTTP/1.1 401 Unauthorized

unauthorized
~~~

Handler `privateData` không chạy vì filter không gọi `next.handle(request)`.

**Request 3 — có API key:**

~~~bash
curl -i http://localhost:8080/api/private \
  -H "X-Api-Key: demo-secret"
~~~

Body:

~~~text
private-data
~~~

**Request 4 — top-level route:**

~~~bash
curl -i http://localhost:8080/public
~~~

Body:

~~~text
public
~~~

Response vẫn có `X-Response-Filter` và log `after` ở builder ngoài, nhưng không có header `X-Request-Source` do `before` chỉ nằm trong builder `/api`.

Các dòng log status có dạng:

~~~text
GET /api/hello -> 200 OK
GET /api/private -> 401 UNAUTHORIZED
GET /api/private -> 200 OK
GET /public -> 200 OK
~~~

Cách hiển thị status cụ thể phụ thuộc implementation `HttpStatusCode.toString()`; đây là hình dạng log dự kiến, không phải contract định dạng log cho production.

**Lưu ý demo:** API key cố định chỉ dùng để minh họa short-circuit. Không lưu secret trực tiếp trong source code, không tự xây hệ thống xác thực production bằng một phép so sánh header.

## 12. Kiểm thử bằng WebTestClient

Có thể kiểm tra các filter ở cấp HTTP thay vì gọi trực tiếp handler:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FunctionalFilterTests {

    @Autowired
    WebTestClient client;

    @Test
    void beforeAndResponseFilterAreApplied() {
        client.get()
                .uri("/api/hello")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("X-Response-Filter", "applied")
                .expectBody(String.class)
                .isEqualTo("hello; source=router-before");
    }

    @Test
    void apiKeyFilterCanShortCircuit() {
        client.get()
                .uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectBody(String.class)
                .isEqualTo("unauthorized");
    }

    @Test
    void validApiKeyCallsTheHandler() {
        client.get()
                .uri("/api/private")
                .header("X-Api-Key", "demo-secret")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("private-data");
    }

    @Test
    void topLevelRouteIsOutsideApiBeforeScope() {
        client.get()
                .uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals("X-Response-Filter", "applied")
                .expectBody(String.class)
                .isEqualTo("public");
    }
}
~~~

Đây là **đoạn test minh họa**, cần imports JUnit, `@Autowired`, `@SpringBootTest`, `WebTestClient` và dependency test của Spring Boot. Nó giả định application và route bean ở phần trước nằm trong cùng application context.

Các test này xác nhận:

- Header từ `before` đến được handler.
- Response filter thêm header đúng.
- Filter có thể trả 401 mà không chạy handler.
- Credentials hợp lệ cho phép handler chạy.
- Phạm vi nested builder được giữ đúng.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `before` để gọi database hoặc WebClient | Callback không hỗ trợ Publisher; dễ block event-loop | Dùng HandlerFilterFunction với Mono/Flux |
| Nghĩ `after` xử lý được exception | Không có response để truyền vào callback nếu handler lỗi | Dùng filter onErrorResume hoặc RouterFunctions.Builder.onError |
| Quên gọi `next.handle(request)` | Handler không được chạy; filter có thể short-circuit ngoài ý muốn | Gọi next ở nhánh được phép |
| Gọi `next.handle(request)` nhiều lần | Có thể thực thi handler nhiều lần và lặp side effect | Thiết kế một lần chuyển tiếp rõ ràng |
| Gọi `subscribe()` trong filter | Mất lifecycle/error/cancel/backpressure của chain | Trả Mono từ filter và compose |
| Dùng `block()` để chờ auth service | Chặn thread, có thể làm nghẽn Netty event-loop | Compose bằng flatMap |
| Đặt filter ở builder top-level quá rộng | Route public/health có thể bị áp chính sách không cần thiết | Đặt filter trong nested builder đúng phạm vi |
| Nghĩ nested filter tự áp dụng route top-level | Route top-level không nằm trong scope nested | Gắn filter tại builder chứa route cần lọc |
| Sửa trực tiếp ServerRequest/ServerResponse | Contract bất biến; sao chép status/header không tự sao chép body | Dùng `ServerRequest.from`; tạo response có body rõ ràng hoặc thêm header toàn cục bằng `WebFilter` |
| Đọc request body trong filter để log rồi gọi next | Body stream có thể đã bị tiêu thụ | Thiết kế buffer/replay có giới hạn hoặc không đọc body |
| Log toàn bộ request/response | Có thể lộ password, token, dữ liệu cá nhân | Chọn field an toàn, redaction và giới hạn log |
| Dùng HandlerFilterFunction cho tất cả controller | Filter chỉ áp dụng RouterFunction, không tự bao phủ annotated controller | Dùng WebFilter khi cần phạm vi toàn WebFlux |
| Tự xử lý CORS bằng header tùy tiện | Bỏ sót preflight, credentials và policy | Dùng CorsWebFilter/CORS config chuẩn |
| Coi API key filter demo là production security | Thiếu rotation, secret storage, identity và authorization | Dùng Spring Security và cơ chế xác thực phù hợp |
| Chỉ test handler, không test filter chain | Bỏ sót lỗi scope, order và short-circuit | Test HTTP bằng WebTestClient |

## 14. Checklist thiết kế filter trước khi production

- [ ] Xác định filter áp dụng cho một route, một nhóm nested routes hay toàn ứng dụng.
- [ ] Chọn `before` nếu chỉ biến đổi request đồng bộ.
- [ ] Chọn `after` nếu chỉ cần quan sát/biến đổi response đồng bộ.
- [ ] Chọn `HandlerFilterFunction` nếu cần reactive I/O, short-circuit, response mapping hoặc error handling.
- [ ] Kiểm tra mọi nhánh có quyền truy cập đều gọi `next.handle(request)` đúng một lần.
- [ ] Không gọi `subscribe()` hoặc `block()` trong filter.
- [ ] Không tiêu thụ request/response body chỉ để log nếu không có cơ chế replay/buffering an toàn.
- [ ] Dùng WebFilter cho chính sách toàn WebFlux application.
- [ ] Dùng Spring Security cho authentication và authorization thực tế.
- [ ] Dùng CORS infrastructure chuẩn.
- [ ] Không để secret hoặc payload nhạy cảm trong log/response.
- [ ] Test nested scope, route top-level, response header, 401/403, error và cancellation.
- [ ] Xác minh thứ tự filter khi có nhiều lớp hoặc `andThen`.
- [ ] Đo latency và overhead của filter trên workload gần production.

## 15. Tự kiểm tra

**Câu 1.** `before` có thể trả `Mono<ServerRequest>` không?

Không. Nó nhận `Function<ServerRequest, ServerRequest>` đồng bộ. Nếu cần request processor bất đồng bộ, dùng `HandlerFilterFunction` hoặc adapter phù hợp.

**Câu 2.** `after` có thể gọi handler lần nữa không?

Không nên. `after` nhận response đã được handler tạo và xử lý response đó. Điều khiển việc gọi handler thuộc `filter`.

**Câu 3.** `filter` có bắt buộc gọi `next.handle(request)` không?

Không. Filter có thể tự trả response để chặn request. Nếu cho phép xử lý tiếp, nó gọi next.

**Câu 4.** `HandlerFilterFunction` có áp dụng cho mọi controller annotation không?

Không. Nó thuộc WebFlux.fn và RouterFunction. Muốn áp dụng ở WebFlux request chain trên toàn ứng dụng, dùng WebFilter.

**Câu 5.** Vì sao filter thích hợp hơn before khi cần kiểm tra quyền qua Mono<Boolean>?

Vì `filter` trả `Mono<ServerResponse>` và có thể compose bất đồng bộ; `before` chỉ là hàm request → request đồng bộ.

**Câu 6.** Filter nằm trong nested builder `/admin` có tác động `/public` không?

Không. Filter chỉ áp dụng cho các route được tạo bởi builder tương ứng. `/public` nằm ở builder ngoài.

**Câu 7.** `after` có chạy nếu handler phát lỗi không?

Thông thường không, vì callback cần một response thành công để nhận làm đầu vào. Muốn quan sát lỗi, dùng filter/error handling.

**Câu 8.** `ServerResponse` muốn thêm header sau khi handler trả response thì làm gì?

Đặt header trong `ServerResponse` khi handler tạo response; với header toàn cục, dùng `WebFilter` trước lúc commit. `ofResponseProcessor` phù hợp để quan sát/biến đổi reactive, nhưng `ServerResponse.from(response)` không tự giữ body.

**Câu 9.** Vì sao không đọc body trong filter rồi gọi next như bình thường?

Body là stream; việc đọc có thể tiêu thụ dữ liệu. Muốn đọc rồi chuyển tiếp cần chiến lược buffer/replay có giới hạn và quản lý tài nguyên.

**Câu 10.** Khi nào dùng WebFilter thay cho HandlerFilterFunction?

Khi chính sách phải áp dụng cho toàn bộ WebFlux WebHandler chain, bao gồm cả functional endpoints và annotated controllers.

## 16. Tài liệu tham khảo chính thức

- [Spring Framework — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): RouterFunction, HandlerFunction, nested routes và filtering handler functions.
- [Spring Framework — HandlerFilterFunction JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/HandlerFilterFunction.html): chữ ký filter, apply, andThen, ofRequestProcessor và ofResponseProcessor.
- [Spring Framework — RouterFunctions.Builder JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.Builder.html): before, after, filter, onError, path, nest và build.
- [Spring Framework — ServerRequest JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html): request access và ServerRequest.from.
- [Spring Framework — ServerResponse JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): response builder và ServerResponse.from.
- [Spring Framework — Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): WebFilter, WebHandler chain và CORS.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): cách Spring Boot đăng ký WebFilter và thứ tự filter.
- [Spring Security — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): bảo vệ ứng dụng WebFlux bằng security chain.

**Ghi nhớ:** `before` biến đổi request đồng bộ, `after` xử lý response đồng bộ, còn `HandlerFilterFunction` bao quanh handler và có thể xử lý bất đồng bộ, short-circuit hoặc thay response. Phạm vi của filter phụ thuộc RouterFunction.Builder nơi nó được đăng ký: nested filter chỉ áp dụng cho nested routes, còn filter của builder ngoài bao phủ các route thuộc builder đó. Dùng WebFilter cho chính sách toàn WebFlux, Spring Security cho xác thực/phân quyền và CORS infrastructure chuẩn cho CORS.
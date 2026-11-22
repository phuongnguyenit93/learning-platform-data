# HttpHandler, WebHandler và ServerWebExchange — nền tảng xử lý HTTP trong Spring WebFlux

## 1. Vấn đề: giữa socket HTTP và @RestController có những lớp nào?

Khi một client gửi `GET /api/exchange/hello/Lan` tới ứng dụng Spring WebFlux, người viết controller thường chỉ thấy `@GetMapping` và `Mono<T>`. Tuy nhiên framework cần giải quyết nhiều việc trước và sau khi gọi controller:

- Nhận request/response từ Reactor Netty, Tomcat, Jetty hoặc một runtime HTTP tương thích.
- Biểu diễn HTTP request/response qua abstraction chung không phụ thuộc implementation server.
- Cung cấp một đối tượng đại diện **toàn bộ trao đổi HTTP**: attributes, locale, web session, principal, request path, multipart/form data, response lifecycle.
- Cho `WebFilter` áp dụng logic trước/sau handler.
- Định tuyến tới annotated controller, functional endpoint hoặc handler tùy biến.
- Áp dụng codec, xử lý exception, viết body bất đồng bộ và kết thúc response.
- Giữ đúng quy tắc Reactive Streams và phối hợp khi client chậm, hủy yêu cầu hoặc socket gặp lỗi.

Ba abstraction quan trọng nhất ở tầng hạ tầng là:

1. `HttpHandler` — hợp đồng HTTP **thấp nhất** của Spring WebFlux, nhận `ServerHttpRequest` và `ServerHttpResponse`, trả `Mono<Void>`.
2. `WebHandler` — hợp đồng xử lý HTTP ở tầng web cao hơn, nhận `ServerWebExchange`, trả `Mono<Void>`.
3. `ServerWebExchange` — ngữ cảnh đại diện cho **một cuộc trao đổi request–response** với các services HTTP/web liên quan.

Ba khái niệm này **không tương đương** với `HandlerFunction` (functional routing) hay `DispatcherHandler` (front controller của WebFlux). Chúng nằm ở những tầng khác nhau và kết nối qua `HttpWebHandlerAdapter` / `WebHttpHandlerBuilder`.

**Phạm vi bài:** Spring Framework **6.1.x**, Spring Boot **3.3.5**, Java **17**, stack **Spring WebFlux**. Bài sử dụng Reactor `Mono`/`Flux`, `WebFilter`, `WebExceptionHandler`, `WebTestClient` và mock HTTP classes. Nó không giả định chỉ Reactor Netty mới chạy WebFlux; WebFlux có adapters cho các runtime được Spring hỗ trợ.

### Sau bài này bạn sẽ biết

- Vẽ đúng đường đi từ adapter HTTP đến `DispatcherHandler` và bộ xử lý result.
- Đọc chữ ký Java của `HttpHandler`, `WebHandler` và `WebFilter`.
- Hiểu vì sao `ServerWebExchange` khác request/response objects và khác `ServerRequest` của functional endpoint.
- Sử dụng request attributes, headers, query, session, principal, locale và response đúng vòng đời.
- Hiểu thứ tự `WebFilter`, `WebExceptionHandler`, định tuyến và serialization.
- Lắp một `HttpHandler` từ `WebHandler` thủ công và biết khi nào không nên làm vậy.
- Tạo ứng dụng WebFlux với WebFilter/controller, chạy curl và test end-to-end bằng `WebTestClient`.
- Tránh các lỗi blocking event-loop, body bị subscribe hai lần, response đã commit, bỏ quên cancellation và rò rỉ DataBuffer.

## 2. Bức tranh lớn của WebFlux

Một ứng dụng Spring Boot WebFlux dùng runtime Reactor Netty thường có đường đi như sau:

```text
HTTP client
   |
   v
Runtime HTTP server: Reactor Netty / supported adapter
   |
   v
ServerHttpRequest + ServerHttpResponse
   |
   v
HttpHandler (low-level reactive HTTP contract)
   |
   v
HttpWebHandlerAdapter
   |  tạo ServerWebExchange, thiết lập services
   v
WebExceptionHandler chain
   |
   v
WebFilter chain
   |
   v
WebHandler
   |
   +--- DispatcherHandler (WebFlux front controller, thường dùng)
   |      |
   |      +--> HandlerMapping tìm endpoint
   |      +--> HandlerAdapter gọi handler
   |      +--> HandlerResultHandler ghi kết quả
   |
   +--- hoặc một WebHandler tùy chỉnh nếu application xây low-level
   |
   v
Response commit + write + completion signals
   |
   v
HTTP client
```

Sơ đồ mô tả trách nhiệm **logic**, không thể hiện một thread riêng cho từng hình hộp. `WebHttpHandlerBuilder` lắp chuỗi các thành phần; việc decorator/filter/exception handler bao quanh có ảnh hưởng tới signal propagation khi thành công hoặc gặp lỗi.

**Điểm phân biệt:** `DispatcherHandler` **là một implementation của WebHandler**. Nó không thay thế abstraction `HttpHandler`; adapter ở phía ngoài vẫn nhận request/response từ HTTP server. Các annotated controllers và WebFlux.fn routes được đặt dưới `DispatcherHandler` qua HandlerMapping/Adapter/ResultHandler.

### Bốn tầng không nên nhầm

| Tầng | Hợp đồng | Biết gì? | Vai trò |
| --- | --- | --- | --- |
| Server adapter | API Reactor Netty, Servlet async/non-blocking bridge, v.v. | Socket/server-specific events | Chuyển server I/O sang Spring HTTP |
| `HttpHandler` | `handle(ServerHttpRequest, ServerHttpResponse)` | HTTP request/response dạng reactive | Entry point độc lập server |
| `WebHandler` | `handle(ServerWebExchange)` | Ngữ cảnh web đã có request, response và services | Thực thi web handling chain |
| WebFlux programming model | Annotated controllers hoặc `RouterFunction`/`HandlerFunction` | Route, DTO, return values | Logic endpoint ứng dụng |

Dù tên "handler" xuất hiện ở nhiều nơi, API và điểm móc hoàn toàn khác nhau.

## 3. HttpHandler: hợp đồng ở tầng HTTP thấp nhất

### 3.1. Chữ ký cốt lõi

`HttpHandler` thuộc package `org.springframework.http.server.reactive`:

```java
@FunctionalInterface
public interface HttpHandler {
    Mono<Void> handle(
            ServerHttpRequest request,
            ServerHttpResponse response);
}
```

Đây là chữ ký ý nghĩa của interface, không phải source file cần tự định nghĩa.

- `ServerHttpRequest` biểu diễn method, URI, headers, path, body as `Flux<DataBuffer>`, cookies, remote address và các metadata HTTP.
- `ServerHttpResponse` cho phép đặt status/headers/cookies và ghi response body bằng `Publisher<? extends DataBuffer>`.
- `Mono<Void>` biểu diễn **completion signal** của việc xử lý request. Nó có thể complete thành công, complete với error hoặc bị cancel; không chứa DTO Java trực tiếp.

**Không đồng nghĩa void method sync:** `Mono<Void>` không có value nhưng vẫn phải được **subscribe bởi framework/runtime**. Nếu tự gọi handler trong test hoặc custom adapter, phải subscribe/verify completion; nếu không, một chuỗi phản ứng có thể chưa chạy và response chưa được ghi.

### 3.2. Ví dụ HttpHandler đơn giản

```java
HttpHandler handler = (request, response) -> {
    response.setStatusCode(HttpStatus.OK);
    response.getHeaders().setContentType(
            MediaType.TEXT_PLAIN);

    byte[] bytes = "hello-low-level"
            .getBytes(StandardCharsets.UTF_8);
    DataBuffer body = response.bufferFactory().wrap(bytes);

    return response.writeWith(Mono.just(body));
};
```

Đây là snippet với imports `HttpHandler`, `HttpStatus`, `MediaType`, `DataBuffer`, `Mono` và `StandardCharsets`. Trong một app thật, HTTP runtime cần được nối với HttpHandler; đoạn này **không tự tạo server đang lắng nghe port**.

Chú ý:

- Không tự `response.getOutputStream().write(...)` kiểu Servlet sync.
- `writeWith` nhận một `Publisher<DataBuffer>`; framework/container sẽ phối hợp write/complete theo reactive contract.
- Không giữ `DataBuffer` dùng lại giữa requests hoặc đưa cùng buffer cho nhiều consumers.
- Với buffer allocation đặc biệt (pooled buffer), quyền sở hữu và release rất quan trọng; xem phần 16.
- Logic low-level không có sẵn controller mapping, validation DTO, handler adapters hay WebSession services nếu bạn không tự lắp.
- Trong Spring Boot application thông thường, bạn **không cần đăng ký HttpHandler bằng tay** chỉ để làm một REST API.

### 3.3. Tại sao Spring cần một hợp đồng chung?

Các HTTP runtimes có API socket/stream khác nhau. Spring định nghĩa `HttpHandler` để framework xử lý reactive requests mà không buộc annotated controllers phụ thuộc trực tiếp vào Netty channel hoặc Servlet response object. Một adapter phía server chuyển request bytes thành `ServerHttpRequest`/`ServerHttpResponse` rồi gọi `HttpHandler`; Spring framework xử lý phần tiếp theo.

Nhờ lớp này, concept WebFlux ở tầng web không phải đổi khi runtime đổi từ Netty sang một server hỗ trợ khác. Tuy vậy, hành vi cụ thể về HTTP/2, TLS, compression, connection timeouts và native buffers vẫn tùy server/proxy configuration; abstraction không làm mọi runtime có cùng performance profile.

## 4. WebHandler: ngữ cảnh web cao hơn HttpHandler

`WebHandler` nằm ở `org.springframework.web.server`:

```java
@FunctionalInterface
public interface WebHandler {
    Mono<Void> handle(ServerWebExchange exchange);
}
```

Đây là signature đại diện API, không phải một custom interface ứng dụng cần viết.

Khác với `HttpHandler`, WebHandler **không** nhận hai arguments request và response trực tiếp. Nó nhận `ServerWebExchange` chứa cả request/response và web infrastructure.

Ví dụ:

```java
WebHandler handler = exchange -> {
    ServerHttpResponse response = exchange.getResponse();
    response.setStatusCode(HttpStatus.OK);
    response.getHeaders().setContentType(
            MediaType.TEXT_PLAIN);

    String path = exchange.getRequest()
            .getPath().value();

    DataBuffer bytes = response.bufferFactory()
            .wrap(path.getBytes(StandardCharsets.UTF_8));

    return response.writeWith(Mono.just(bytes));
};
```

Đây là một **WebHandler snippet**; có thể bọc nó bằng `WebHttpHandlerBuilder.webHandler(handler).build()` để tạo HttpHandler thật, như test hoàn chỉnh ở mục 11.

### WebHandler không phải HandlerFunction

Có hai tên dễ gây nhầm:

| Type | Package | Method | Vị trí |
| --- | --- | --- | --- |
| `WebHandler` | `org.springframework.web.server` | `handle(ServerWebExchange) -> Mono<Void>` | Hạ tầng WebFlux |
| `HandlerFunction<T>` | `org.springframework.web.reactive.function.server` | `handle(ServerRequest) -> Mono<ServerResponse>` | WebFlux.fn programming model |
| `HandlerMethod` | Spring web method metadata | Method Java của annotated controller | MVC/WebFlux annotated mapping |
| `HttpHandler` | `org.springframework.http.server.reactive` | `handle(ServerHttpRequest,ServerHttpResponse) -> Mono<Void>` | Tầng HTTP thấp |

`HandlerFunction` tạo `ServerResponse` như một kết quả function-level; `WebHandler` chịu trách nhiệm hoàn thành HTTP exchange (hoặc delegate cho `DispatcherHandler` xử lý results). `ServerRequest` của WebFlux.fn cũng khác với `ServerHttpRequest` low-level và `ServerWebExchange`.

## 5. ServerWebExchange: trung tâm của một HTTP exchange

`ServerWebExchange` thuộc `org.springframework.web.server`, tượng trưng cho một request/response exchange đang diễn ra.

Các API hay dùng:

| Thành phần | Ví dụ | Tác dụng |
| --- | --- | --- |
| Request | `exchange.getRequest()` | Method, URL, headers, cookies, body publisher |
| Response | `exchange.getResponse()` | Status, headers, cookies, write/commit |
| Attributes | `exchange.getAttributes()` | Mutable map dữ liệu gắn với exchange hiện tại |
| Attribute | `exchange.getAttribute("key")` | Lấy attribute có type do caller dự kiến |
| Default attribute | `exchange.getAttributeOrDefault("key", fallback)` | Đặt giá trị fallback khi key không tồn tại |
| Web session | `exchange.getSession()` | `Mono<WebSession>`, reactive session access |
| Principal | `exchange.getPrincipal()` | `Mono<Principal>` hoặc subtype, tùy authentication |
| Locale | `exchange.getLocaleContext()` | LocaleContext theo resolver |
| Form data | `exchange.getFormData()` | `Mono<MultiValueMap<String,String>>` |
| Multipart data | `exchange.getMultipartData()` | `Mono<MultiValueMap<String,Part>>` |
| URL transform | `exchange.transformUrl(String)` | Áp dụng URL transformer nếu cấu hình |
| Conditional request | `exchange.checkNotModified(...)` | Hỗ trợ đánh giá conditional GET theo API |
| Request mutation | `exchange.mutate().request(...).build()` | Tạo exchange wrapper phục vụ filters |

### 5.1. Attributes sống trong phạm vi exchange

```java
exchange.getAttributes().put(
        "requestMarker", "from-filter");

String marker = exchange.getAttributeOrDefault(
        "requestMarker", "absent");
```

**Đây không phải HTTP header, không phải Session và không phải Reactor Context.** Attributes là map nội bộ, tiện để filters trao thông tin với handler trong một request. Đừng đặt secrets vào logs chỉ vì chúng nằm trong attributes. Với logic đi qua nhiều async publishers, exchange có thể được các stages cùng thấy; việc ghi nhiều threads vào mutable map cần xem xét synchronization/happens-before.

Một key khác nhau ở nhiều thư viện có thể collision; dùng constants/namespaced keys như `com.example.trace.correlationId` thay vì `id` hoặc `user` chung chung.

### 5.2. getSession() trả publisher

```java
Mono<WebSession> sessionMono =
        exchange.getSession();
```

Không làm:

```java
// PHẢN VÍ DỤ: có thể block event loop.
WebSession session = exchange.getSession().block();
```

Đúng hơn:

```java
return exchange.getSession()
        .flatMap(session -> {
            String value = session.getAttribute("theme");
            return buildResponse(value);
        });
```

Đây là **snippet** vì `buildResponse` do application triển khai. Session là asynchronous abstraction có thể tương tác session store. Việc gọi `getSession()` **không nhất thiết đồng nghĩa tạo một session cookie mới**; việc start/commit session phụ thuộc cách sử dụng và session manager.

### 5.3. Principal cũng là reactive

```java
return exchange.getPrincipal()
        .map(Principal::getName)
        .defaultIfEmpty("anonymous");
```

`getPrincipal()` trả `Mono<Principal>`; có thể empty khi chưa được xác thực. Đừng dùng `getAttribute("user")` tùy tiện để thay authentication; khi thêm Spring Security, hãy dùng security context/principal từ framework và kiểm tra quyền theo resource/tenant.

**Quan trọng:** Nếu ứng dụng có Spring Security WebFlux, authentication/authorization nằm trong reactive `WebFilter` chain do Spring Security quản lý. Không tin giá trị header `X-User` của client làm identity chỉ vì WebFilter có thể gắn attribute.

### 5.4. Request path và URI không giống servletRequest

Trong WebFlux, `ServerHttpRequest` cung cấp `getPath()` và `getURI()`. Một request path có thể có context path và pathWithinApplication; HTTP URI raw/decoded segments cần xử lý đúng khi routing/security. Không giả định có `HttpServletRequest` sẵn trong app chạy Netty. Các APIs `jakarta.servlet.http.HttpServletRequest` thuộc Servlet stack và không phải portable WebFlux code.

### 5.5. Một exchange, một response lifecycle

`ServerWebExchange` gắn với một HTTP exchange. Nó không được lưu trong singleton field hoặc lưu vô thời hạn trong queue để tái sử dụng cho request khác. Response có giai đoạn **committed**: khi status/headers/body đã được commit, việc đổi status/headers hoặc gửi một error JSON mới có thể không còn khả thi.

Kiểm tra:

```java
if (exchange.getResponse().isCommitted()) {
    return Mono.error(error);
}
```

Đây là snippet với `error` đã có. Việc kiểm tra `isCommitted()` không giải quyết toàn bộ race; đôi khi commit xảy ra ngay sau check. Thiết kế error policies nên xử lý lỗi **trước** khi bắt đầu stream body hoặc chấp nhận chỉ có thể đóng kết nối khi streaming response đã gửi một phần.

## 6. HttpWebHandlerAdapter: cầu nối hai hợp đồng

`HttpWebHandlerAdapter` thuộc `org.springframework.web.server.adapter`. Về vai trò, nó **nhận** low-level request/response từ `HttpHandler` và **thích nghi** thành `ServerWebExchange` để gọi một `WebHandler`.

```text
HttpHandler.handle(ServerHttpRequest, ServerHttpResponse)
                 |
                 v
         HttpWebHandlerAdapter
                 |
                 +-- tạo ServerWebExchange
                 +-- session manager
                 +-- codec config cho form/multipart
                 +-- locale resolver
                 +-- forwarded-header handling nếu cấu hình
                 |
                 v
WebHandler.handle(ServerWebExchange)
                 |
                 v
          Mono<Void> completion
```

Nó còn tham gia các xử lý HTTP lifecycle như response logging, request details, session save, cleanup và lỗi theo integration cụ thể. Ở mức API ứng dụng, **nên để `WebHttpHandlerBuilder` hoặc Spring Boot dựng adapter**, không new thủ công adapter khi chưa hiểu dependencies/chain.

### Vì sao builder giúp giảm lỗi?

Một WebHandler đơn lẻ chưa nói các filters/exceptions/session/codec đã có chưa. `WebHttpHandlerBuilder` gom các cấu hình liên quan để tạo thành HttpHandler hoàn chỉnh, tránh bỏ quên WebFilter hoặc WebExceptionHandler khi tự xây một custom reactive HTTP server adapter.

## 7. WebHttpHandlerBuilder lắp chuỗi xử lý

`org.springframework.web.server.adapter.WebHttpHandlerBuilder` có hai cách khởi tạo đáng nhớ:

```java
HttpHandler fromContext =
        WebHttpHandlerBuilder
                .applicationContext(applicationContext)
                .build();

HttpHandler manual =
        WebHttpHandlerBuilder
                .webHandler(webHandler)
                .filter(myWebFilter)
                .exceptionHandler(myErrorHandler)
                .build();
```

Đây là **snippet**: `applicationContext`, `webHandler`, `myWebFilter` và `myErrorHandler` là các instances đã được cung cấp. Dùng static `applicationContext(...)` khi muốn builder tự dò Spring-managed beans; dùng `webHandler(...)` khi chủ động cung cấp target.

Theo Spring 6.1, builder có thể nhận biết các loại bean/điểm cấu hình như sau:

| Bean hoặc dependency | Số lượng/điều kiện khái niệm | Nhiệm vụ |
| --- | --- | --- |
| `WebHandler` tên `webHandler` | Một target | Trong Boot WebFlux thường là DispatcherHandler |
| `WebFilter` | 0..N, ordered | Chặn/bao quanh request chain |
| `WebExceptionHandler` | 0..N, ordered | Xử lý lỗi từ filter/handler chain |
| `WebSessionManager` tên `webSessionManager` | Optional | Quản lý WebSession |
| `ServerCodecConfigurer` tên `serverCodecConfigurer` | Optional | Readers cho form/multipart và codec settings |
| `LocaleContextResolver` tên `localeContextResolver` | Optional | Locale context |
| `ForwardedHeaderTransformer` tên chuẩn của framework | Optional | Xử lý Forwarded/X-Forwarded-* từ proxy theo trust policy |
| HTTP handler decorators / observation support | Tùy version/config | Decorate tổng thể HttpHandler, observability |

`WebHttpHandlerBuilder.applicationContext(context)` tìm `WebHandler` theo tên hạ tầng chuẩn `webHandler`, thường do WebFlux config khai báo cho `DispatcherHandler`; filters/exception handlers tìm theo type và sắp thứ tự. Trong app Boot chuẩn, **không cần tự dựng bean HttpHandler cùng tên** vì Boot/WebFlux configuration đã lắp pipeline.

### Thứ tự WebFilter và WebExceptionHandler

Về bản chất builder dựng một **target WebHandler**, bọc bằng các `WebFilter` rồi bọc bằng các `WebExceptionHandler`. Điều đó cho phép exception handlers thấy lỗi phát sinh cả khi filter hoặc handler ở bên trong báo error.

```text
WebExceptionHandler A
   |
   +--> WebExceptionHandler B
          |
          +--> WebFilter A
                 |
                 +--> WebFilter B
                        |
                        +--> WebHandler
```

Sơ đồ chỉ minh họa **nesting**. Thứ tự thực tế phụ thuộc `Ordered`/`@Order` và component registration; không suy luận sequence chính xác từ tên class A/B. Xác minh thứ tự/filter chain với tests khi business/security correctness phụ thuộc nó.

### Không đặt custom WebHandler bean tên webHandler vô ý

Trong Boot WebFlux, `DispatcherHandler` thường chính là WebHandler trung tâm với bean name `webHandler`. Nếu bạn tự tạo một bean `WebHandler` tên `webHandler` mà không có chủ đích thay toàn bộ dispatch pipeline, có thể làm mất route discovery cho annotated controllers/functional endpoints hoặc gây bean collision. Với custom API thông thường, dùng `@RestController`, `RouterFunction`, `WebFilter` hoặc WebFlux config thay vì override front controller.

## 8. DispatcherHandler: WebHandler thực hiện web routing

`org.springframework.web.reactive.DispatcherHandler` là front controller của WebFlux. Nó implement `WebHandler` và có thể được phát hiện dưới tên bean `webHandler`.

Ba nhóm extension chính:

1. **HandlerMapping**: tìm handler đầu tiên match request (annotated controller, functional route hoặc handler khác).
2. **HandlerAdapter**: thực thi handler được chọn và trả `HandlerResult`.
3. **HandlerResultHandler**: xử lý kết quả để tạo HTTP response (body, `ResponseEntity`, functional `ServerResponse` hoặc view).

```text
DispatcherHandler.handle(exchange)
            |
            v
HandlerMapping(s): matching handler?
            |
            v
HandlerAdapter: invoke handler -> HandlerResult
            |
            v
HandlerResultHandler: render response
            |
            v
          Mono<Void>
```

### Các loại handler mapping

- `RequestMappingHandlerMapping`: annotated `@RequestMapping`, `@GetMapping`, `@PostMapping`.
- `RouterFunctionMapping`: WebFlux.fn `RouterFunction<ServerResponse>`.
- `SimpleUrlHandlerMapping`: mappings tường minh URL → WebHandler/handler khác.

### Các loại result handlers

- `ResponseEntityResultHandler` cho `ResponseEntity`.
- `ServerResponseResultHandler` cho WebFlux functional `ServerResponse`.
- `ResponseBodyResultHandler` cho `@ResponseBody`/`@RestController` objects.
- `ViewResolutionResultHandler` cho HTML views/model theo configuration.

Mục tiêu là hỗ trợ nhiều programming models phía trên một WebHandler/HttpHandler pipeline thống nhất.

**Không nhầm:** WebFlux `DispatcherHandler` **khác** Spring MVC `DispatcherServlet`. WebFlux có thể chạy trên Servlet containers bằng bridge non-blocking I/O, nhưng nó vẫn dùng **reactive WebFlux processing contracts**, không tự trở thành MVC DispatcherServlet.

## 9. WebFilter: xử lý trước/sau ở tầng exchange

`WebFilter` có chữ ký:

```java
public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain);
}
```

Bạn thường trả `chain.filter(exchange)` để tiếp tục. Có thể:
- Đọc request metadata và gắn attributes cho downstream.
- Set headers trước khi response commit.
- Logging/tracing/metrics/correlation hoặc policy có phạm vi rõ.
- Dừng chain sớm bằng một `Mono<Void>` trả response cụ thể.
- Dùng reactive operators `doOnError`, `doFinally`, `contextWrite` theo semantics Reactor.

Ví dụ:

```java
@Component
@Order(-10)
public class MarkerWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {
        exchange.getAttributes().put(
                "demo.marker", "from-web-filter");

        exchange.getResponse().getHeaders()
                .set("X-WebFilter", "active");

        return chain.filter(exchange);
    }
}
```

Đây là **snippet class đầy đủ về logic**; cần imports `Component`, `Order`, `WebFilter`, `ServerWebExchange`, `WebFilterChain`, `Mono`. Phiên bản runnable tại mục 11 có scope `/api/exchange/**` rõ ràng.

### Gọi chain đúng một lần

```java
return chain.filter(exchange);
```

Không làm:

```java
// PHẢN VÍ DỤ: multiple subscriptions có thể thực hiện xử lý lần hai.
chain.filter(exchange).subscribe();
return chain.filter(exchange);
```

Spring/HTTP runtime subscribe outer Mono. Tự `subscribe()` có thể kích hoạt second request processing, mất context/cancellation, race response và data corruption. Cũng không được `block()` trong WebFilter event loop.

### Chặn request từ filter

Một filter có thể trả 403/429 mà không gọi downstream handler:

```java
if (blockedByServerSidePolicy(exchange)) {
    exchange.getResponse().setStatusCode(
            HttpStatus.TOO_MANY_REQUESTS);
    return exchange.getResponse().setComplete();
}
return chain.filter(exchange);
```

Đây là snippet với `blockedByServerSidePolicy` cần implement ở business/security policy. **Không dùng header do client tự khai để xác nhận user là admin**. Authn/authz production nên đặt trong Spring Security reactive security chain, kết hợp service-level permission checks.

### WebFilter so với GatewayFilter, HandlerFilterFunction và Servlet Filter

| API | Thuộc stack/phạm vi | Điểm khác |
| --- | --- | --- |
| `WebFilter` | WebFlux WebHandler chain | Trước/bao quanh DispatcherHandler hoặc target WebHandler |
| `HandlerFilterFunction` | WebFlux.fn router/handler | Chỉ bọc functional router/handler tương ứng |
| `GlobalFilter`/`GatewayFilter` | Spring Cloud Gateway | Là abstraction riêng của Gateway, không đồng nghĩa mọi WebFlux app |
| `jakarta.servlet.Filter` | Servlet stack | Filter chain ở Servlet container |
| `HandlerInterceptor` | Spring MVC | Dựa trên MVC HandlerMapping lifecycle |

Một WebFlux app có thể chạy trên Servlet container, nhưng WebFilter vẫn là reactive API ở WebHandler chain; nó **không tự giống** Servlet Filter dùng `doFilter`.

## 10. WebExceptionHandler: chặn lỗi trong reactive chain

`WebExceptionHandler` thuộc `org.springframework.web.server`:

```java
public interface WebExceptionHandler {
    Mono<Void> handle(
            ServerWebExchange exchange,
            Throwable ex);
}
```

Nó xử lý error signal ở tầng WebHandler chain. Nếu **không xử lý**, trả `Mono.error(ex)` để error handlers tiếp theo có cơ hội xử lý hoặc runtime kết thúc với lỗi. Nếu xử lý thành công, đặt status/headers/body thích hợp và trả một Mono complete.

Ví dụ cho custom exception nội bộ:

```java
WebExceptionHandler handler = (exchange, ex) -> {
    if (!(ex instanceof IllegalArgumentException)) {
        return Mono.error(ex);
    }
    if (exchange.getResponse().isCommitted()) {
        return Mono.error(ex);
    }

    exchange.getResponse().setStatusCode(
            HttpStatus.BAD_REQUEST);
    exchange.getResponse().getHeaders().setContentType(
            MediaType.TEXT_PLAIN);

    byte[] bytes = "bad request"
            .getBytes(StandardCharsets.UTF_8);
    DataBuffer body = exchange.getResponse()
            .bufferFactory().wrap(bytes);
    return exchange.getResponse()
            .writeWith(Mono.just(body));
};
```

Đây là **snippet handler**; không thêm nó bừa vào production. `IllegalArgumentException` có thể đại diện bug programmer, không chỉ bad user input; nên dùng domain exception cụ thể, status contract/`ProblemDetail` ổn định và security-safe logging. Khi response đã commit, không được cố đổi 200 thành 400 và viết JSON mới.

### WebExceptionHandler khác @ExceptionHandler

`@ExceptionHandler`/`@RestControllerAdvice` thường thuộc cơ chế xử lý exception trong annotated controller adapter. `WebExceptionHandler` nằm **ngoài** ở WebHandler chain và có thể bắt lỗi từ filter hoặc handler không được xử lý ở tầng bên trong. Nó không có nghĩa mọi exception bắt buộc phải đi qua global handler: exceptions có thể đã được xử lý bởi annotated advice, result adapter hoặc WebFlux infrastructure trước đó.

Spring Boot còn có error web exception handlers được auto-configured để tạo responses cho các lỗi chưa được ứng dụng xử lý. Nếu thêm custom WebExceptionHandler, cần xem `@Order`/status/error body để không đè/che lỗi framework hoặc leak thông tin.

## 11. Dự án Spring Boot 3.3.5 runnable với ServerWebExchange

Project demo minh họa:

1. WebFlux chạy trên **Reactor Netty** qua `spring-boot-starter-webflux`.
2. `@RestController` dùng `ServerWebExchange` để đọc request path/method và attributes.
3. Một `WebFilter` đánh dấu exchange và thêm response header.
4. Một endpoint trả `Mono.delay` để cho thấy reactive async completion (không dùng `Thread.sleep`).
5. Một endpoint tạo `ResponseStatusException` để thử error status.
6. `WebTestClient` test trên **embedded HTTP server thật** với port ngẫu nhiên.
7. Một test low-level tạo `HttpHandler` từ `WebHandler` bằng `WebHttpHandlerBuilder`, không mở socket thật.

Không có database, OAuth, Spring Security hay logging PII; chương trình chỉ để học abstraction/lifecycle.

### 11.1. Cấu trúc project

```text
webflux-infra-demo/
├── pom.xml
└── src/
    ├── main/java/demo/webflux/
    │   ├── WebFluxInfraApplication.java
    │   ├── ExchangeController.java
    │   └── MarkerWebFilter.java
    └── test/java/demo/webflux/
        ├── ExchangeControllerTest.java
        └── LowLevelHttpHandlerTest.java
```

### 11.2. pom.xml

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
    <artifactId>webflux-infra-demo</artifactId>
    <version>1.0.0</version>
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

Không thêm `spring-boot-starter-web`, để Boot chọn reactive web application type từ WebFlux starter. Nếu thêm cả Servlet MVC và WebFlux starters cùng lúc, Boot thường ưu tiên Servlet MVC application type trừ khi cấu hình khác; **không dùng classpath hỗn hợp làm bằng chứng WebFlux đang active**.

### 11.3. Main application

**`src/main/java/demo/webflux/WebFluxInfraApplication.java`**

```java
package demo.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxInfraApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxInfraApplication.class, args);
    }
}
```

### 11.4. WebFilter đặt marker vào ServerWebExchange

**`src/main/java/demo/webflux/MarkerWebFilter.java`**

```java
package demo.webflux;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-10)
public class MarkerWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest()
                .getPath().value();

        if (!path.startsWith("/api/exchange/")) {
            return chain.filter(exchange);
        }

        exchange.getAttributes().put(
                "demo.marker", "from-web-filter");
        exchange.getResponse().getHeaders()
                .set("X-WebFilter", "active");

        return chain.filter(exchange);
    }
}
```

**Giải thích:**

- `@Component` đăng ký WebFilter ở Spring context; framework có thể đưa nó vào WebHandler chain.
- `@Order(-10)` cho thứ tự tương đối so với các filters khác, không có nghĩa nó an toàn khi chặn/mở security một mình.
- `exchange.getAttributes()` chia sẻ dữ liệu trong một exchange, không gửi marker như request header lên server khác.
- `X-WebFilter` được ghi trước khi response commit.
- Filter chỉ tác động tới đường bắt đầu `/api/exchange/` và luôn gọi downstream chain **một lần**.
- Không có `block()` hoặc `subscribe()` thủ công.
- Nếu body streaming đã commit, thay đổi headers sau đó không bảo đảm có hiệu lực; ví dụ gắn trước để dễ đoán.

### 11.5. REST controller nhận ServerWebExchange

**`src/main/java/demo/webflux/ExchangeController.java`**

```java
package demo.webflux;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/exchange")
public class ExchangeController {

    @GetMapping("/hello/{name}")
    public Mono<ResponseEntity<Map<String, String>>> hello(
            @PathVariable String name,
            ServerWebExchange exchange) {

        String marker = exchange.getAttributeOrDefault(
                "demo.marker", "missing");
        String method = exchange.getRequest()
                .getMethod().name();

        Map<String, String> body = Map.of(
                "name", name,
                "marker", marker,
                "method", method);

        return Mono.just(ResponseEntity.ok(body));
    }

    @GetMapping("/async")
    public Mono<Map<String, String>> async() {
        return Mono.delay(Duration.ofMillis(20))
                .map(tick -> Map.of("state", "ready"));
    }

    @GetMapping("/fail")
    public Mono<String> fail() {
        return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "invalid request"));
    }
}
```

**Những gì code chứng minh:**

- `@RestController` chỉ là programming model ở trên WebFlux `DispatcherHandler`; ở hạ tầng vẫn có HttpHandler, WebHandler và exchange.
- `ServerWebExchange` được framework inject vào controller argument mà không cần tự tạo.
- Filter đặt `demo.marker` vào map attributes, controller đọc lại marker đó.
- `getRequest().getMethod()` lấy `HttpMethod` của request; endpoint là GET nên method mong đợi là "GET".
- `Mono<ResponseEntity<Map<...>>>` là reactive single-value response; Jackson serialize Map thành JSON.
- `Mono.delay(...)` phát signal sau một khoảng thời gian mà không giữ một thread ngủ chờ riêng cho mỗi subscription theo kiểu `Thread.sleep`. Tuy nhiên bản demo không phải benchmark và runtime vẫn cần scheduler/event-loop threads.
- `Mono.error(new ResponseStatusException(...))` dẫn tới HTTP 400 qua WebFlux error machinery. Response body/error details có thể thay đổi theo Boot configuration; test chỉ assert status để tránh phụ thuộc định dạng mặc định.
- Ứng dụng không truy cập blocking JDBC, không tự subscribe, không giữ `ServerWebExchange` trong singleton field.

### 11.6. Chạy bằng Maven và curl

Từ thư mục `webflux-infra-demo` với Java 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Đây là hai lệnh **chạy tuần tự**. Khi Boot khởi động trên port mặc định 8080:

```bash
curl -i 'http://localhost:8080/api/exchange/hello/Lan'
```

Các phần chính của response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-WebFilter: active

{"name":"Lan","marker":"from-web-filter","method":"GET"}
```

Thứ tự các keys JSON do serializer quyết định, không dùng string equality trên toàn JSON nếu không cần.

```bash
curl -i 'http://localhost:8080/api/exchange/async'
```

Dự kiến status 200, header `X-WebFilter: active` và JSON:

```json
{"state":"ready"}
```

```bash
curl -i 'http://localhost:8080/api/exchange/fail'
```

Dự kiến HTTP status **400 Bad Request**. Header từ filter có thể vẫn được gửi nếu response chưa commit; error body tùy cấu hình `ErrorWebExceptionHandler` và content negotiation.

Với `curl -i` không có caching/retry mặc định tương đương browser. Nếu chạy sau proxy, quan sát thêm forwarded headers, idle timeout, `Content-Length`/chunked transfer và Content-Encoding; các giá trị ấy phụ thuộc runtime.

## 12. Test WebTestClient: đường thực qua HttpHandler tới Controller

**`src/test/java/demo/webflux/ExchangeControllerTest.java`**

```java
package demo.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ExchangeControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void exchangeAttributesFlowFromWebFilterToHandler() {
        client.get()
              .uri("/api/exchange/hello/Lan")
              .exchange()
              .expectStatus().isOk()
              .expectHeader().valueEquals(
                      "X-WebFilter", "active")
              .expectBody()
              .jsonPath("$.name").isEqualTo("Lan")
              .jsonPath("$.marker")
                  .isEqualTo("from-web-filter")
              .jsonPath("$.method").isEqualTo("GET");
    }

    @Test
    void asynchronousPublisherCompletesWithBody() {
        client.get()
              .uri("/api/exchange/async")
              .exchange()
              .expectStatus().isOk()
              .expectHeader().valueEquals(
                      "X-WebFilter", "active")
              .expectBody()
              .jsonPath("$.state").isEqualTo("ready");
    }

    @Test
    void errorSignalBecomesBadRequestStatus() {
        client.get()
              .uri("/api/exchange/fail")
              .exchange()
              .expectStatus().isBadRequest();
    }
}
```

Ba tests này khởi động embedded HTTP server trên một port ngẫu nhiên. `WebTestClient` gửi request đến server thật, nên đi qua reactive server adapter và toàn bộ WebFlux infrastructure. Điều đó **khác** với gọi trực tiếp controller method mà không có dispatcher, filter hoặc serializer.

Không khẳng định body errors như `{"message":"invalid request"}` sẽ luôn xuất hiện: trong Boot default và tùy `server.error.include-message`, error response details có thể thay đổi. Tập trung kiểm tra status và behavior đã khai báo.

## 13. Test HttpHandler thấp hơn DispatcherHandler, không cần mở port

Để phân biệt `HttpHandler` và `WebHandler`, ta xây một pipeline low-level trong test độc lập: không có `@RestController`, không có `DispatcherHandler`, nhưng vẫn có `ServerWebExchange`/`WebFilter` vì `WebHttpHandlerBuilder` tạo adapter.

**`src/test/java/demo/webflux/LowLevelHttpHandlerTest.java`**

```java
package demo.webflux;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.HttpHandler;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpResponse;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebHandler;
import org.springframework.web.server.adapter.WebHttpHandlerBuilder;

import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LowLevelHttpHandlerTest {

    @Test
    void adapterBuildsExchangeAndRunsWebFilter() {
        WebHandler target = exchange -> {
            String marker = exchange.getAttributeOrDefault(
                    "demo.marker", "missing");

            exchange.getResponse().setStatusCode(HttpStatus.OK);
            exchange.getResponse().getHeaders().setContentType(
                    MediaType.TEXT_PLAIN);

            DataBuffer buffer = exchange.getResponse()
                    .bufferFactory()
                    .wrap(marker.getBytes(StandardCharsets.UTF_8));

            return exchange.getResponse()
                    .writeWith(Mono.just(buffer));
        };

        WebFilter markerFilter = (exchange, chain) -> {
            exchange.getAttributes().put(
                    "demo.marker", "seen-by-web-handler");
            return chain.filter(exchange);
        };

        HttpHandler handler = WebHttpHandlerBuilder
                .webHandler(target)
                .filter(markerFilter)
                .build();

        MockServerHttpRequest request =
                MockServerHttpRequest.get("/raw/demo").build();
        MockServerHttpResponse response =
                new MockServerHttpResponse();

        handler.handle(request, response)
                .block(Duration.ofSeconds(2));

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("seen-by-web-handler",
                response.getBodyAsString()
                        .block(Duration.ofSeconds(2)));
    }
}
```

**Điều bài test chứng minh:**

1. Test tự định nghĩa **WebHandler** chứ không định nghĩa annotated controller.
2. Một **WebFilter** thêm attribute `demo.marker` vào exchange.
3. `WebHttpHandlerBuilder.webHandler(target).filter(markerFilter).build()` tạo **HttpHandler** từ các lớp cấp web.
4. Test gọi `HttpHandler.handle(MockServerHttpRequest, MockServerHttpResponse)` — tầng thấp nhất sau HTTP server adapter.
5. `HttpWebHandlerAdapter` bên trong tạo exchange, WebFilter chạy trước target.
6. `getBodyAsString()` kiểm tra bytes được viết thành HTTP response.
7. `block()` **chỉ nằm trong test** để chờ completion; không dùng `block()` trong server handler/WebFilter chạy trên event loop.

Nếu chạy Maven với cả `ExchangeControllerTest` và `LowLevelHttpHandlerTest`, project có **4 test methods**. Khi tất cả pass, Maven exit code `0`; summary thông thường sẽ có tổng `Tests run: 4, Failures: 0, Errors: 0, Skipped: 0`. Bài này cung cấp mã được rà soát tĩnh theo các APIs Spring Boot 3.3.5; không khẳng định đã chạy Maven trong quá trình biên soạn trên Google Sheets.

### Khi nào tự build HttpHandler là hợp lý?

- Khi tích hợp Spring WebFlux với một custom HTTP runtime/adapter.
- Khi unit test một WebHandler/filter chain thấp hơn DispatcherHandler.
- Khi xây reusable reactive HTTP infrastructure module cần kiểm soát session/codec/exception chains.
- Khi quan sát/đo đạc toàn bộ HTTP exchange ở lớp low-level.

**Không** phải lựa chọn mặc định để thêm một endpoint REST: `@RestController` hoặc WebFlux.fn `RouterFunction` dễ maintain, có JSON codecs, validation/route tooling và error handling đầy đủ hơn.

## 14. ServerWebExchange trong filters: mutate request đúng cách

Các exchange wrappers hỗ trợ thay đổi request metadata theo functional style:

```java
ServerWebExchange updated = exchange.mutate()
        .request(builder -> builder.header(
                "X-Internal-Trace", "trace-generated-server-side"))
        .build();

return chain.filter(updated);
```

Đây là snippet đặt trong `WebFilter.filter(...)`. Chú ý:

- Header `X-Internal-Trace` ở đây chỉ là **ví dụ**; auth/identity không được lấy từ header client tùy ý.
- Khi tạo request wrapper, phải truyền **updated exchange** cho chain, không bỏ qua biến updated.
- Mutation không làm request bytes được giải mã/re-encode tự động. Với body transformations, cần `ServerHttpRequestDecorator`, `DataBuffer`, codecs và cancellation/backpressure handling đúng.
- Không tự sửa URI/Host/Forwarded headers từ input user để đổi route sang tài nguyên admin.
- Khi framework đã cung cấp Spring Security/tracing gateway integration, ưu tiên công cụ chính thức hơn một filter tự viết phức tạp.

### Attributes hay Reactor Context?

`exchange.getAttributes()` là dữ liệu gắn với **một exchange object**. `reactor.util.context.Context` là context đi cùng reactive subscription, dùng cho cross-cutting data như tracing/security/reactive transaction.

```java
return chain.filter(exchange)
        .contextWrite(context ->
                context.put("auditTag", "from-webfilter"));
```

Snippet trên thêm `auditTag` vào Reactor Context cho các publishers **upstream của contextWrite theo quy tắc Reactor Context propagation**. Nó không tự thay đổi `exchange.getAttributes()`, và `ThreadLocal` cũng không tự đồng bộ với Reactor Context. Cách truy cập Context bên trong reactive chain thường dùng `Mono.deferContextual(...)`; không nên dùng `Thread.currentThread()` làm request identity.

**Đừng nhầm ba nơi:**
- Request headers: dữ liệu HTTP client/proxy gửi (có thể chưa đáng tin).
- Exchange attributes: mutable map của web exchange.
- Reactor Context: subscription-scoped context lan qua reactive operators, dùng bởi nhiều infrastructure integrations.

## 15. Form/multipart data, body publisher và single subscription

`ServerWebExchange` có `getFormData()` và `getMultipartData()`, trả `Mono<MultiValueMap<...>>`. Nó cung cấp parsed/cached view theo request content type, dựa vào cấu hình readers. Nhưng raw `ServerHttpRequest.getBody()` là `Flux<DataBuffer>`, thường là **one-shot stream**.

### 15.1. Không đọc body hai lần tùy tiện

Phản ví dụ:

```java
// PHẢN VÍ DỤ: subscribe raw body để log rồi downstream lại đọc.
exchange.getRequest().getBody()
        .subscribe(buffer -> logBuffer(buffer));
return chain.filter(exchange);
```

Đoạn này có thể tiêu thụ stream trước body decoder của controller, gây lỗi unreadable/empty body, mất cancellation context và rò rỉ DataBuffer nếu không release. Không log raw body chứa passwords/tokens/PII.

Muốn observability cho request body, nên dùng framework tooling được thiết kế cho streaming, hoặc viết `ServerHttpRequestDecorator` có giới hạn tối đa bytes, buffering/ref-count và backpressure, test content-length/transfer-encoding, slow clients, errors và cancel. Đừng mặc định "WebFilter luôn có thể đọc body mà không ảnh hưởng controller".

### 15.2. Đừng block khi đọc multipart/form data

```java
return exchange.getMultipartData()
        .flatMap(parts -> {
            // validate metadata/Part, enforce limits
            return processParts(parts);
        });
```

Đây là snippet vì `processParts` do application tự định nghĩa. Multipart body có thể lớn; phải giới hạn upload size, số parts, file names/path traversal, content type, temp storage và virus/malware scanning theo threat model. Reactive multipart APIs không tự làm file an toàn.

### 15.3. Streaming response và cancellation

Nếu client ngắt kết nối khi stream lớn, reactive pipeline có thể nhận **cancel signal**. Nguồn dữ liệu phải giải phóng subscriptions, file handles, Netty buffers và remote connections đúng. Với `Flux<DataBuffer>`, backpressure thể hiện demand nhưng chỉ hiệu quả khi source thực sự tôn trọng demand; một `Flux.create` đẩy vô hạn lên bộ nhớ có thể OOM dù giao diện là reactive.

## 16. Response commit, headers và beforeCommit

`ServerHttpResponse` có trạng thái commit. Với response thông thường, status/headers cần được đặt **trước** khi body bắt đầu ghi. Để gắn logic cuối trước commit, response hỗ trợ `beforeCommit(Supplier<? extends Mono<Void>>)`:

```java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .add("X-Before-Commit", "yes");
    return Mono.empty();
});

return chain.filter(exchange);
```

Đây là snippet trong WebFilter. Callback phải trả một **deferred Mono** nếu có async side effect; callback chỉ có tác dụng trước commit, không cho phép chỉnh status/header sau khi response đã được gửi. Tránh blocking work trong callback; response commit phase không phải nơi gọi DB dài hoặc remote API sync.

### Lỗi sau khi đã ghi một phần body

Giả sử stream đã gửi một nửa CSV rồi publisher báo error. `WebExceptionHandler` có thể thấy error signal, nhưng response có thể đã commit 200 và gửi bytes. Nó không thể bảo đảm chuyển thành 500 JSON đúng contract; thường chỉ có thể kết thúc/đóng connection hoặc xử lý theo protocol streaming (SSE event riêng nếu còn write được).

Với endpoint tải file, SSE hoặc chunked response:
- Đặt headers/status/authorization trước body.
- Điều khiển error/cancellation, body buffers và timeout.
- Nếu có content checksum, trả metadata/streaming protocol được thiết kế rõ.
- Không hứa với client rằng mọi lỗi đều được map thành JSON 500 sau khi streaming bắt đầu.

## 17. WebFlux backpressure và non-blocking: những gì thật sự được bảo đảm

`HttpHandler.handle(...)` trả `Mono<Void>` và body request/response dùng Reactive Streams. Điều này **cho phép** runtime/pipeline thực hiện I/O không chặn và truyền backpressure signals. Nhưng không thể kết luận mọi code Spring WebFlux đều non-blocking chỉ vì signatures dùng Mono/Flux.

Phản ví dụ:

```java
@GetMapping("/broken")
public Mono<String> broken() {
    String result = blockingJdbcRepository.load();
    return Mono.just(result);
}
```

Đây là snippet với repository chưa định nghĩa, cố ý minh họa lỗi. Lời gọi JDBC đồng bộ chạy **ngay khi controller method được gọi** và có thể block event loop.

Một cách offload có giới hạn nếu tạm thời phải dùng thư viện blocking:

```java
return Mono.fromCallable(
            () -> blockingJdbcRepository.load())
        .subscribeOn(Schedulers.boundedElastic());
```

Đây cũng là snippet, dùng `reactor.core.scheduler.Schedulers`. Nó **chuyển nơi blocking work diễn ra** sang boundedElastic worker, **không biến JDBC thành non-blocking**. Cần cấu hình connection pool, statement timeouts, bounds, transaction context và đo throughput; tránh làm quá nhiều blocking jobs/hàng đợi gây latency.

### Những resource vẫn tồn tại

Khi một request đang chờ reactive signal:
- Socket/connection và HTTP exchange state vẫn tồn tại.
- Buffers, codec objects, subscriptions và timeouts vẫn có thể chiếm memory.
- Scheduler/event-loop threads vẫn chạy callbacks/serialization.
- DB/network pool bottlenecks không tự biến mất.

Reactive giúp xử lý nhiều pending operations với ít blocked threads **khi toàn pipeline non-blocking và backpressure-aware**. Không tự động tăng throughput cho CPU-bound work hoặc downstream chậm.

## 18. Spring Security, CORS, forwarded headers và privacy

### 18.1. Security ở đâu?

Trong Spring Security WebFlux, security chain nằm trong **WebFilter chain**. Một SecurityWebFilterChain có các rules về authentication, authorization, CSRF, CORS và exception handling. Nó bảo vệ request **trước annotated controller/WebFlux.fn**, không phụ thuộc route style.

Không dùng:

```java
// PHẢN VÍ DỤ: client tự đặt header.
String user = exchange.getRequest()
        .getHeaders().getFirst("X-User");
exchange.getAttributes().put("authenticatedUser", user);
```

để thay Spring Security. Header này do client kiểm soát và không chứng minh danh tính. Khi cần principal, truy cập `exchange.getPrincipal()` hoặc reactive SecurityContext theo framework và áp quyền resource/tenant ở service.

### 18.2. CORS ở WebFlux layer

CORS ảnh hưởng browser. Có thể xử lý qua WebFlux CORS configuration hoặc `CorsWebFilter`, và khi thêm Security cần thứ tự integration đúng. Không tự viết WebFilter luôn trả `Access-Control-Allow-Origin: *` cho endpoint có credentials. CORS **không phải authentication**; command-line HTTP clients có thể gửi request dù browser cross-origin policy không cho đọc response.

### 18.3. Forwarded/X-Forwarded-* headers

`ServerWebExchange` sử dụng request metadata đã qua server/proxy adapter. Nếu hệ thống đứng sau reverse proxy, public scheme/host/prefix có thể đến từ `Forwarded` hoặc `X-Forwarded-*`; `ForwardedHeaderTransformer` cần trust model rõ. Proxy tin cậy phải **loại bỏ headers giả mạo từ Internet rồi đặt giá trị chuẩn**. Nếu tin client-supplied `X-Forwarded-Host`, app có thể sinh URL/redirect sai, dẫn tới phishing, open redirects hoặc cache poisoning.

### 18.4. Session và cache

`WebSession` có thể mang state user nhưng không biến các HTTP responses thành private automatically. Endpoint cá nhân hóa cần `Cache-Control: private` hoặc `no-store` theo mức nhạy cảm và policy CDN. Không lấy `exchange.getSession()` rồi mặc định shared proxies sẽ phân biệt users đúng.

## 19. Logging, observability và debugging

Một pipeline reactive có thể chuyển execution thread giữa nhiều scheduler; vì vậy gắn correlation ID bằng plain `ThreadLocal` không đảm bảo giữ được xuyên async operators.

Nên dùng:
- Spring/Micrometer observation integration và tracing context propagation được framework hỗ trợ.
- Reactor Context cho dữ liệu subscription-scoped.
- Exchange attributes cho thông tin ngắn hạn request-scoped.
- Sanitized logs: method, route template, status, latency, correlation ID; **không log tokens, raw cookies hoặc request body nhạy cảm**.
- Ordered WebFilters và error handlers với trách nhiệm riêng, không để logging filter nuốt mọi exception.

### Các bước debug

1. **Xác nhận stack thật**: ứng dụng Spring Boot có WebFlux active, không phải MVC `DispatcherServlet` vô tình được chọn do classpath.
2. Xác nhận `WebHandler` bean tên `webHandler` và `DispatcherHandler` được WebFlux configuration phát hiện; không override nhầm.
3. Quan sát từ `HttpHandler` đến `WebHttpHandlerBuilder`/`HttpWebHandlerAdapter` rồi WebFilters; test low-level nếu cần.
4. Kiểm tra `HandlerMapping` nào match route và `HandlerResultHandler` nào ghi response.
5. Với header thiếu, kiểm tra có đặt trước commit không, filter có gọi chain không.
6. Với 404, xem path mapping/controller/functional predicates trước khi nghi Netty.
7. Với body rỗng, xem ai subscribe/consume request body trước converter.
8. Với timeout, xem downstream client/database, event-loop blocking, queue và network idle timeout.
9. Với 500, xác định exception đã xảy ra trước hay sau response commit.
10. Với memory leak, kiểm tra `DataBuffer` pooling, body caching và cancellation cleanup.
11. Với mất principal/MDC, xem SecurityContext/Reactor Context và scheduler boundaries.
12. Với CORS errors, test OPTIONS/preflight Origin thực qua security filter chain.

## 20. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Import `web.servlet.function.ServerRequest` trong WebFlux | Nhầm MVC.fn với WebFlux.fn | Dùng `web.reactive.function.server` |
| Tạo WebHandler rồi nghĩ có routing/JSON tự động | WebHandler chỉ nhận exchange | Dùng DispatcherHandler/config hoặc tự xử lý toàn pipeline |
| Override bean `webHandler` làm annotated controllers mất | Đè front controller WebFlux | Không override trừ khi đang xây low-level infrastructure |
| Thêm starter-web và starter-webflux, controller chạy MVC | Boot ưu tiên MVC app type trong case thông thường | Định rõ stack, dependencies, integration tests |
| `Mono<Void>` không làm gì trong custom test | Chưa subscribe/chờ completion | WebTestClient hoặc `block` trong test, không ở event loop |
| Filter chạy hai lần | Gọi `subscribe()` rồi lại return chain | Trả chain một lần, không subscribe thủ công |
| Lỗi `block()` trên event-loop | Gọi blocking API trong reactive callback | Non-blocking client hoặc bounded offload |
| Body request trống | WebFilter đọc raw body trước decoder | Không consume raw body hai lần, decorate/cache đúng |
| JSON malformed bị trả 500 sai schema | Error handler/codecs/advice khác mong đợi | Test status/content-type, consistent errors |
| Không set được status trong WebExceptionHandler | Response đã committed | Xử lý errors sớm, streaming-specific policy |
| Response header mất | Gắn sau khi body đã commit | Đặt trước hoặc `beforeCommit` |
| Filter order gây security bypass | Trust boundary/order không rõ | Spring Security reactive chain + test |
| ThreadLocal mất traceId | Reactive scheduler changes | Reactor Context/context propagation |
| Multipart OOM | Buffer hết body vào memory không giới hạn | Max in-memory size, streaming, upload limits |
| DataBuffer memory leak | Pooled buffers không được release khi filter thao tác | Dùng framework operators/`DataBufferUtils.release` đúng ownership |
| `getSession().block()` gây stall | Blocking event loop | flatMap/reactive composition |
| `ServerWebExchange` bị lưu trong singleton | Mix nhiều requests, giữ resources lâu | Chỉ giữ dữ liệu cần thiết và lifecycle ngắn |
| Wrong Host ở URLs | Untrusted forwarded headers/proxy config | Sanitize tại ingress, canonical base |
| SSE chậm, memory tăng | Producer không tôn trọng demand/cancel | Backpressure, buffer bounds, proper disposal |
| HTTP response khác giữa Netty/Servlet bridge | Server-specific behavior / proxy | Integration tests theo runtime thực |

## 21. Lựa chọn mức API nào khi xây ứng dụng?

| Nhu cầu | Điểm tích hợp nên chọn |
| --- | --- |
| CRUD REST JSON bình thường | `@RestController` hoặc WebFlux.fn `RouterFunction` |
| Áp dụng policy chung trước routes | `WebFilter` hoặc Spring Security WebFilter chain |
| Map lỗi HTTP chưa được xử lý | `WebExceptionHandler` hoặc Boot/WebFlux error mechanisms phù hợp |
| Dùng chung state request qua filters/controllers | `ServerWebExchange.getAttributes()` với keys rõ |
| Đọc body/multipart ở business logic | Annotated binding/WebFlux.fn readers/codecs; tránh raw buffer khi không cần |
| Quan sát toàn bộ handler pipeline | Observability / WebFilter / HttpHandler decorators khi cần |
| Thay đổi implementation HTTP runtime | Adapter integration dựa trên `HttpHandler` |
| Xây custom routing engine | `WebHandler`/`HandlerMapping` khi thực sự cần |
| Test full HTTP chain | `WebTestClient` bind to server/context |
| Test WebHandler/HttpHandler lower layer | `MockServerHttpRequest` + `MockServerHttpResponse` + WebHttpHandlerBuilder |

**Nguyên tắc:** chọn abstraction ở mức cao nhất đủ đáp ứng yêu cầu. Controller/router APIs ít gây lỗi low-level body handling hơn. Chỉ tự xây HttpHandler khi có nhu cầu hạ tầng thật.

## 22. Câu hỏi tự kiểm tra

1. `HttpHandler.handle` nhận những parameters nào và trả kiểu gì?
2. `WebHandler.handle` khác `HttpHandler.handle` ở đầu vào thế nào?
3. `ServerWebExchange` cung cấp gì ngoài `ServerHttpRequest` và `ServerHttpResponse`?
4. `WebHttpHandlerBuilder` làm hai việc chính nào?
5. `HttpWebHandlerAdapter` tạo abstraction nào để WebHandler xử lý?
6. `DispatcherHandler` có phải một implementation của WebHandler không?
7. Phân biệt `HandlerMapping`, `HandlerAdapter` và `HandlerResultHandler`.
8. Một `WebFilter` có được tự gọi `subscribe()` để chạy chain không?
9. Vì sao `WebExceptionHandler` có thể không đổi được HTTP status khi lỗi xảy ra giữa response stream?
10. `exchange.getAttributes()` có tương đương Reactor Context hoặc WebSession không?
11. Vì sao `exchange.getSession()` và `exchange.getPrincipal()` trả Mono?
12. `WebMvc.fn HandlerFunction` có giống `WebHandler` của WebFlux không?
13. Nếu ứng dụng có Spring Boot WebFlux với annotated controllers, có nên tự tạo `WebHandler` bean tên `webHandler` không?
14. `Mono<Void>` không phát value nhưng đóng vai trò gì ở response completion?
15. Nếu WebFilter đọc raw `getBody()` rồi controller cũng đọc JSON, rủi ro gì?
16. `DataBuffer` được pool thì vì sao reference counting/release quan trọng?
17. Khi nào dùng `beforeCommit`?
18. Thêm `subscribeOn(Schedulers.boundedElastic())` quanh JDBC có khiến JDBC non-blocking không?
19. Tại sao WebFilter nên không thay Spring Security cho authentication/authorization?
20. Làm sao test low-level HttpHandler mà không cần khởi động Netty server?
21. Tại sao `ForwardedHeaderTransformer` cần trust boundary?
22. Khi có query/form/multipart data, tại sao phải kiểm soát max size và cancellation?
23. Nếu filter ghi error response, có phải luôn tiếp tục `chain.filter(exchange)` không?
24. Nếu endpoint trả `Mono.error`, response error body chắc chắn giống giữa mọi Boot configurations không?

**Gợi ý:** (1) ServerHttpRequest, ServerHttpResponse → Mono<Void>. (2) Exchange bao request, response và web services. (3) Attributes, session, principal, form/multipart, locale, conditionals. (4) Lắp filter/error chain và adapt thành HttpHandler. (5) ServerWebExchange. (6) Có. (7) Chọn handler, thực thi, render result. (8) Không. (9) Response đã commit. (10) Không. (11) Reactive asynchronous services. (12) Không, package và abstraction khác. (13) Tránh override front controller. (14) Completion/error/cancel signals. (15) Body one-shot bị tiêu thụ hoặc leak. (16) Pooled memory phải trả lại. (17) Logic header ngay trước commit. (18) Không, chỉ chuyển nơi block. (19) Không đủ trust/security policy. (20) WebHttpHandlerBuilder + mock HTTP request/response. (21) Client có thể giả headers. (22) Chống OOM/slow clients. (23) Nếu đã short-circuit thì không gọi tiếp. (24) Không, tùy error handlers và Boot config.

## 23. Tài liệu tham khảo chính thức

- [Spring Framework 6.1 — WebFlux: Reactive Core / HttpHandler & WebHandler](https://docs.spring.io/spring-framework/reference/6.1/web/webflux/reactive-spring.html)
- [Spring Framework 6.1 — DispatcherHandler](https://docs.spring.io/spring-framework/reference/6.1/web/webflux/dispatcher-handler.html)
- [Spring Framework 6.1 — WebHttpHandlerBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html)
- [Spring Framework 6.1 — HttpWebHandlerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/web/server/adapter/HttpWebHandlerAdapter.html)
- [Spring Framework 6.1 — ServerWebExchange Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/web/server/ServerWebExchange.html)
- [Spring Framework 6.1 — WebHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/web/server/WebHandler.html)
- [Spring Framework 6.1 — WebFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/web/server/WebFilter.html)
- [Spring Framework 6.1 — WebExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/web/server/WebExceptionHandler.html)
- [Spring Framework 6.1 — HttpHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/http/server/reactive/HttpHandler.html)
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html)
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — Reactive Web Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)

**Tổng kết:** `HttpHandler` là entry point reactive HTTP thấp nhất, xử lý `ServerHttpRequest` và `ServerHttpResponse`. `HttpWebHandlerAdapter` thích nghi chúng thành `ServerWebExchange` và gọi `WebHandler`; `WebHttpHandlerBuilder` lắp WebFilters, WebExceptionHandlers cùng các services cần thiết. Trong ứng dụng WebFlux thông thường, `DispatcherHandler` chính là WebHandler trung tâm để thực hiện annotated controllers/WebFlux.fn routes. Nắm đúng các tầng này giúp bạn viết filters, xử lý errors, tích hợp Security, quan sát HTTP requests và debug reactive I/O mà không nhầm WebFlux với Servlet MVC hoặc coi mọi Mono/Flux tự động là non-blocking.

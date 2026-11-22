# WebFilter, WebFilterChain và WebExceptionHandler trong Spring WebFlux

## 1. Mục tiêu bài học

Một ứng dụng WebFlux có thể phục vụ HTTP thông qua annotated `@RestController` hoặc functional `RouterFunction`. Trước khi đến endpoint, request thường cần authentication/authorization, correlation ID, logging an toàn, CORS, tracing, rate limiting; sau đó có thể cần chuẩn hóa một số lỗi và giải phóng tài nguyên. Spring cung cấp các thành phần hạ tầng:

- **`WebFilter`**: can thiệp **trước, xung quanh và sau** phần xử lý request ở tầng WebFlux. Nó nhận `ServerWebExchange` và một `WebFilterChain`, trả `Mono<Void>`.
- **`WebFilterChain`**: đại diện cho **phần còn lại** của pipeline, gồm các WebFilter tiếp theo và `WebHandler` đích. Gọi `chain.filter(exchange)` để chuyển tiếp.
- **`WebExceptionHandler`**: xử lý error signal từ WebFilter chain hoặc target WebHandler khi lỗi chưa được xử lý bên trong, thường bằng cách ghi HTTP status/body nếu response chưa committed.

Tất cả thuộc **Spring WebFlux**, không phải Servlet `Filter` của Spring MVC. Chúng hoạt động ở tầng `org.springframework.web.server`, bên dưới annotated/functional routing. Bài dùng **Java 17, Spring Boot 3.3.5, Spring Framework 6.1.x** và Reactor `Mono`/`Flux`.

Sau bài này, bạn sẽ:
1. Vẽ được thứ tự và trách nhiệm của `HttpHandler`, `WebHandler`, filters, exception handlers và `DispatcherHandler`.
2. Viết filter gọi chain **đúng một lần**, thực hiện logic "before", "after", "finally" và short-circuit.
3. Phân biệt lỗi được handle bởi `@ExceptionHandler` và lỗi rơi tới `WebExceptionHandler`.
4. Hiểu `@Order`, reactive signals (complete/error/cancel), response commit và giới hạn sửa status/body.
5. Dùng `ServerWebExchange` để truyền request-scoped attributes, mutate request/response trước khi commit.
6. Tránh `block()`/`subscribe()` thủ công, tiêu thụ request body hai lần và làm lộ dữ liệu nhạy cảm.
7. Viết ứng dụng chạy thật với Spring Boot WebFlux, hai filters, một custom exception handler, controller và WebTestClient tests.
8. Kiểm tra một chain low-level bằng `WebHttpHandlerBuilder` và mock HTTP objects.
9. Lựa chọn vị trí phù hợp cho Spring Security, CORS, observability, backpressure và exception policies.

## 2. Bản đồ hạ tầng WebFlux

WebFlux định nghĩa hai cấp abstraction xử lý HTTP:

- `HttpHandler.handle(ServerHttpRequest, ServerHttpResponse) -> Mono<Void>`: giao diện tối thiểu giữa Spring và HTTP server adapter.
- `WebHandler.handle(ServerWebExchange) -> Mono<Void>`: tầng web nhận một **exchange** chứa request/response và những services liên quan.

`WebHttpHandlerBuilder` lắp một `WebHandler` mục tiêu với các WebFilter, WebExceptionHandler, rồi dùng `HttpWebHandlerAdapter` để tạo một `HttpHandler` có thể nối với server.

```text
Client HTTP
   |
   v
Reactor Netty / supported reactive server adapter
   |
   v
HttpHandler
   |
   v
HttpWebHandlerAdapter
   |  tạo ServerWebExchange
   v
WebExceptionHandler chain (outer layer)
   |
   +--> WebFilter A
         |
         +--> WebFilter B
                |
                +--> target WebHandler
                       |
                       +--> DispatcherHandler (thường dùng)
                              |
                              +--> HandlerMapping
                              +--> HandlerAdapter
                              +--> HandlerResultHandler
   |
   v
Mono<Void> completion/error/cancellation
   |
   v
ServerHttpResponse commit/write
```

Các hình hộp **không** tương ứng với những thread riêng. Pipeline reactive được thực hiện khi HTTP runtime subscribe; thứ tự callback có thể chịu ảnh hưởng `flatMap`, `publishOn`, `subscribeOn` và I/O async.

Trong Spring Boot WebFlux thông thường, target WebHandler là `DispatcherHandler`. Nó dùng HandlerMapping/HandlerAdapter/HandlerResultHandler cho cả annotated controllers và WebFlux.fn endpoints. **Không cần tự tạo HttpHandler/WebHttpHandlerBuilder trong app REST thông thường**; Boot/WebFlux auto-configuration làm việc đó.

## 3. WebFilter là gì?

Package và interface:

```java
package org.springframework.web.server;

public interface WebFilter {
    Mono<Void> filter(ServerWebExchange exchange,
                      WebFilterChain chain);
}
```

Đây là **chữ ký minh họa** của API, không phải file bạn tự định nghĩa.

- `exchange` đại diện **một HTTP request/response exchange**, có `getRequest()`, `getResponse()`, `getAttributes()`, `getSession()`, `getPrincipal()`...
- `chain` là phần còn lại của pipeline. Nếu filter không gọi chain, target handler sẽ **không tự được chạy**.
- `Mono<Void>` báo completion/error/cancel cho toàn exchange. Đây không phải một DTO response; HTTP body thường do downstream viết qua `ServerHttpResponse`.
- WebFilter có thể chạy cho cả annotated `@RestController` và WebFlux.fn routes nằm dưới WebHandler của application.

### Filter tối giản

```java
@Component
public class RequestMarkerFilter implements WebFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        exchange.getAttributes().put("example.marker", "created");
        return chain.filter(exchange);
    }
}
```

Code là snippet đặt trong project Spring WebFlux, cần imports `Component`, `WebFilter`, `ServerWebExchange`, `WebFilterChain` và `Mono`. Khi Boot scan `@Component`, nó đăng ký filter bean và builder WebFlux có thể đưa filter vào chain.

### Một WebFilter không phải Servlet Filter

| So sánh | WebFlux `WebFilter` | Servlet `Filter` |
| --- | --- | --- |
| Package | `org.springframework.web.server` | `jakarta.servlet` |
| API | `Mono<Void> filter(ServerWebExchange, WebFilterChain)` | `void doFilter(ServletRequest, ServletResponse, FilterChain)` |
| Request context | `ServerWebExchange` | `ServletRequest/HttpServletRequest` |
| Chain delegation | `return chain.filter(exchange)` | `chain.doFilter(request,response)` |
| Completion | Reactive signals | Synchronous/async Servlet lifecycle |
| Framework | Spring WebFlux | Servlet/MVC |
| I/O | Reactive streams, có thể dùng non-blocking server adapters | Servlet I/O; có Servlet async/non-blocking APIs riêng |

**Không chỉ dựa vào tên "Filter".** WebFlux chạy trên Netty không có `HttpServletRequest` bắt buộc, nên code Servlet filter không portable sang WebFlux.

## 4. WebFilterChain điều phối bước tiếp theo

`WebFilterChain` chỉ có trách nhiệm cơ bản:

```java
public interface WebFilterChain {
    Mono<Void> filter(ServerWebExchange exchange);
}
```

**Gọi một lần, return kết quả**:

```java
return chain.filter(exchange);
```

Mỗi filter có thể chọn:
- **Tiếp tục**: `return chain.filter(exchange)`.
- **Chặn**: đặt status và `return exchange.getResponse().setComplete()`.
- **Biến đổi**: tạo exchange wrapper bằng `exchange.mutate()`, rồi truyền wrapper cho chain.
- **Bao quanh**: gắn `doOnError`, `doOnSuccess`, `doFinally`, `onErrorResume` hoặc `contextWrite` lên Mono từ chain.

### Điều gì xảy ra khi không gọi chain?

```java
if (tooManyRequests(exchange)) {
    exchange.getResponse()
            .setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
    return exchange.getResponse().setComplete();
}
return chain.filter(exchange);
```

Đây là snippet có `tooManyRequests` là policy server-side. Nhánh đầu tiên **short-circuit** pipeline và không gọi controller. Cần bảo đảm filter không chỉ return `Mono.empty()` mà bỏ quên status/body, nếu không response có thể là 200 rỗng ngoài ý muốn.

### Không gọi chain hai lần

```java
// SAI: tự subscribe làm pipeline chạy ngoài lifecycle do server quản lý.
chain.filter(exchange).subscribe();
return chain.filter(exchange);
```

Hậu quả có thể là:
- Target handler xử lý hai lần, gây duplicate side effects.
- Hai subscriptions tranh nhau đọc body HTTP (thường one-shot).
- Hai writers cạnh tranh ghi status/body.
- Request cancellation, security context, tracing và error handling không còn gắn với một subscription thống nhất.

**Không `subscribe()` hoặc `block()` bên trong WebFilter chỉ để "ép" chain chạy.** Server runtime subscribe outer Publisher.

## 5. Before, after, errors và cancellation trong Reactor

Một WebFilter có thể đặt logic **trước** `chain.filter` và gắn operators cho kết quả của downstream.

```java
@Override
public Mono<Void> filter(ServerWebExchange exchange,
                         WebFilterChain chain) {
    long startedAt = System.nanoTime();
    String route = exchange.getRequest().getPath().value();

    return chain.filter(exchange)
            .doOnError(error ->
                    log.error("Request failed: {}", route, error))
            .doFinally(signalType -> {
                long elapsedNanos =
                        System.nanoTime() - startedAt;
                metrics.record(route, elapsedNanos, signalType);
            });
}
```

Đây là **snippet** cần `log`/`metrics` do ứng dụng định nghĩa. Không dùng request raw path chứa PII/secrets làm metric tag trong production; ưu tiên route templates/low cardinality, và không log raw query/token.

### Hiểu đúng các operators

| Operator | Khi kích hoạt | Ghi nhớ |
| --- | --- | --- |
| `doOnSubscribe` | Khi subscriber bắt đầu | Không nhất thiết chạy cùng lúc tạo Mono |
| `doOnSuccess` | Mono complete thành công, với Void thường value là null | Không đồng nghĩa status HTTP là 2xx |
| `doOnError` | Mono phát error | Quan sát, **không nuốt error** |
| `doFinally` | Sau terminate/cancel | Thấy `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL` |
| `onErrorResume` | Khi phát error | Có thể thay error thành Publisher khác |
| `contextWrite` | Bổ sung Reactor Context | Subscription context, không phải exchange attributes |
| `then(...)` | Chờ upstream complete rồi chạy downstream | Cần hiểu thời điểm commit/response write |

**HTTP status là metadata, không phải Reactor error signal.** Một handler có thể trả HTTP 404 bằng `ServerResponse.notFound()` và Publisher vẫn complete thành công; `doOnError` sẽ **không** chạy. Ngược lại, có error sau khi body đã commit 200; HTTP status có thể không đổi được. Vì vậy đếm HTTP 4xx/5xx cần nhìn response status, còn đếm reactive failures cần nhìn signals — hai khái niệm khác nhau.

### Logic trước khi subscribe: defer khi cần

Nếu một phép đo hay thao tác có side effect cần chạy đúng thời điểm subscription thay vì lúc tạo Mono, dùng:

```java
return Mono.defer(() -> {
    long start = System.nanoTime();
    return chain.filter(exchange)
            .doFinally(signal ->
                    recordDuration(System.nanoTime() - start, signal));
});
```

Snippet có `recordDuration` giả định. Cách này rõ ràng về tính lazy của reactive pipeline, hữu ích trong tests/retries. Tránh ghi dữ liệu request-specific vào singleton fields.

### Đặt status/header trước khi commit

```java
exchange.getResponse().getHeaders()
        .set("X-Request-Scope", "webflux");

return chain.filter(exchange);
```

Đặt header **trước** delegation cho downstream. Nếu cần làm việc ngay trước commit, có `response.beforeCommit(...)`, nhưng vẫn không được block hoặc thay header sau khi committed.

## 6. Thứ tự nhiều WebFilter

Spring phát hiện các bean `WebFilter`, sắp xếp theo `Ordered`, `@Order` hoặc framework conventions. Trong một pipeline với:

- `@Order(-20)` — filter A.
- `@Order(-10)` — filter B.

Thông thường A là **outer** và B là **inner**; A chạy trước khi gọi B, B trước handler. Sau khi downstream complete, callback "after" có thể diễn ra theo **chiều ngược** vì các publishers lồng nhau:

```text
A before
  B before
    Handler
  B after
A after
```

Thứ tự chính xác của nhiều operators `doOnSuccess`/`doFinally` và asynchronous signal processing cần được test khi quan trọng: `doFinally` chạy khi terminate/cancel và có thể thấy thứ tự callback khác intuitive "stack unwind". Sơ đồ chỉ là model cơ bản.

### Không suy ra thứ tự chỉ từ tên class

`WebHttpHandlerBuilder.applicationContext(...)` dùng ordered discovery. Nếu app có Spring Security WebFilters, tracing filters và custom filters, order của chúng không chỉ là các con số do bạn viết. Đừng tự đặt `@Order(Ordered.HIGHEST_PRECEDENCE)` cho custom filter rồi cho rằng nó luôn nên chạy trước authentication; có thể vô tình bypass hoặc làm sai CORS/CSRF/context propagation.

**Chính sách bảo mật** nên ở Spring Security reactive chain, không ở custom filter dựa trên header do client kiểm soát. Khi thật sự cần order cụ thể, kiểm tra security chain configuration và integration tests.

### Đăng ký filter một lần

`@Component` hoặc `@Bean` thường đủ để builder phát hiện filter. Đừng đồng thời đăng ký cùng object qua cả bean auto-discovery và builder manual nếu không có chủ đích — dễ bị chạy lặp.

## 7. ServerWebExchange: dữ liệu dùng giữa filters và endpoint

`ServerWebExchange` đại diện **một cuộc trao đổi request–response**.

```java
String path = exchange.getRequest().getPath().value();
HttpMethod method = exchange.getRequest().getMethod();

exchange.getResponse().getHeaders()
        .set("X-Policy", "observed");

exchange.getAttributes().put("audit.tag", "ok");
String tag = exchange.getAttributeOrDefault(
        "audit.tag", "missing");
```

Đây là snippet cần imports `HttpMethod`, `ServerWebExchange`. Một số dữ liệu khác:
- `exchange.getPrincipal()` → `Mono<Principal>`, có thể empty.
- `exchange.getSession()` → `Mono<WebSession>`.
- `exchange.getFormData()`/`getMultipartData()` → Mono chứa parsed data.
- `exchange.getLocaleContext()` theo locale resolver.
- `exchange.getResponse().isCommitted()` để nhận biết write lifecycle.
- `exchange.mutate()` để bọc request/response.

### Exchange attributes không phải request headers

`exchange.getAttributes()` là map nội bộ **chỉ tồn tại trong exchange**, không tự được gửi sang client. Đừng dùng một key chung như `user` khiến các thư viện clash; chọn key có namespace như `com.example.trace.id`.

### Exchange attributes khác Reactor Context

| Nơi chứa | Đặc điểm | Dùng phù hợp |
| --- | --- | --- |
| HTTP request headers | Client/proxy cung cấp; có thể giả mạo | Accept, content type, correlation ID sau khi validate |
| Exchange attributes | Mutable map request-scoped | Trao dữ liệu giữa WebFilter và Handler |
| Reactor `Context` | Subscription-scoped immutable context | Reactive tracing/security propagation |
| `WebSession` | State giữa nhiều exchanges theo session policy | Session attributes khi thật sự cần |
| `ThreadLocal` | Thread-bound state | Không tự bảo toàn khi chuyển reactive scheduler |

Dùng `Mono.deferContextual(contextView -> ...)` nếu phải đọc Reactor Context từ reactive pipeline. Không lấy `Thread.currentThread().getName()` làm identity của user và không giả định MDC custom luôn truyền đúng qua event loops.

### Đọc Principal mà không block

```java
return exchange.getPrincipal()
        .map(Principal::getName)
        .defaultIfEmpty("anonymous");
```

Snippet này trả `Mono<String>`. Không gọi `exchange.getPrincipal().block()` trên event loop. Với Spring Security, reactive authentication và authorization nên dùng SecurityContext/Principal tích hợp framework; **không dùng `X-User` header do client tự gửi làm user đã đăng nhập**.

## 8. Mutate request/exchange để chuẩn hóa metadata

`exchange.mutate()` cho phép tạo wrapper view của exchange:

```java
ServerWebExchange nextExchange = exchange.mutate()
        .request(builder ->
                builder.header("X-Internal-Marker", "server-side"))
        .build();

return chain.filter(nextExchange);
```

Đây là snippet trong `WebFilter.filter(...)`. Dùng khi cần thêm header nội bộ do server kiểm soát cho downstream handler. Chỉ `return chain.filter(nextExchange)` mới truyền wrapper cho filter tiếp theo; nếu truyền exchange cũ, thay đổi có thể không đến downstream.

Cẩn thận:
- Không tạo authentication identity từ header chưa xác thực.
- Nếu thay path, routing, host hoặc scheme, ảnh hưởng lớn tới authorization và cache key; cần trust boundary/allowlist.
- Mutate metadata không tự giúp đọc, cache hoặc chuyển đổi body bytes.
- Không lưu `ServerWebExchange` vào singleton state hoặc background queue lâu dài.

## 9. WebExceptionHandler: vai trò và chữ ký

`WebExceptionHandler` nằm ở cùng tầng `org.springframework.web.server` với WebFilter:

```java
@FunctionalInterface
public interface WebExceptionHandler {
    Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
}
```

Đây là chữ ký khái niệm từ Javadoc. Một exception handler được gọi khi phía trong pipeline phát **error signal**. Nó quyết định:

1. Có xử lý loại error này không?
2. Response đã committed chưa?
3. Nếu có thể xử lý: status/headers/body nào sẽ trả client?
4. Nếu không xử lý được: trả `Mono.error(ex)` để handler kế tiếp hoặc runtime xử lý.

**Không trả `Mono.empty()` cho mọi loại lỗi** chỉ để logs sạch; điều đó có thể khiến client nhận status/body không chính xác.

### Xử lý một custom error

```java
WebExceptionHandler handler = (exchange, ex) -> {
    if (!(ex instanceof DemoFailure)) {
        return Mono.error(ex);
    }
    if (exchange.getResponse().isCommitted()) {
        return Mono.error(ex);
    }

    exchange.getResponse()
            .setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
    return exchange.getResponse().setComplete();
};
```

Đây là **snippet**, `DemoFailure` là một custom exception do app định nghĩa. Nó trả 503 không body; bản runnable ở mục 13 trả một JSON error có content type rõ.

### Một WebExceptionHandler bắt lỗi từ đâu?

Nó có thể xử lý lỗi **chưa được xử lý** từ:
- `WebFilter` phía trong.
- Target `WebHandler`, thường là `DispatcherHandler`.
- Handler mapping, controller/handler invocation, response rendering nếu lỗi đi thành Publisher error và response chưa quá muộn.
- Một số lỗi lifecycle bên trong WebHandler chain.

Nó **không** đảm bảo bắt được:
- Lỗi socket/TLS ở HTTP server trước khi tạo exchange.
- Một exception đã được `@ExceptionHandler` hoặc framework handler khác xử lý.
- Một lỗi tự sinh trong detached `subscribe()` mà không thuộc outer pipeline.
- Error đã xảy ra khi HTTP response đã gửi một phần body và cannot be rewritten as normal JSON response.

### Error propagation là phần của reactive contract

```java
return chain.filter(exchange)
        .onErrorResume(MyKnownException.class, error ->
                writeKnownError(exchange, error));
```

Đây là snippet có `writeKnownError` từ app. Nó đặt error handling **trong WebFilter**, có thể ngăn error đi ra `WebExceptionHandler`. Dùng hợp lý với lỗi mà filter sở hữu; với API-wide error policy, có thể chọn một `WebExceptionHandler` được đăng ký/order đúng. Tránh hai tầng cùng bắt một exception và ghi hai lần.

## 10. WebHttpHandlerBuilder lắp filter/error chain

`WebHttpHandlerBuilder` có nhiệm vụ:
1. Lắp một target `WebHandler`, bọc bởi các `WebFilter` rồi bọc thêm các `WebExceptionHandler`.
2. Adapt chain thành `HttpHandler` bằng `HttpWebHandlerAdapter`.

Có thể tạo từ ApplicationContext:

```java
HttpHandler handler = WebHttpHandlerBuilder
        .applicationContext(applicationContext)
        .build();
```

Hoặc lắp manual:

```java
HttpHandler handler = WebHttpHandlerBuilder
        .webHandler(targetWebHandler)
        .filter(firstWebFilter, secondWebFilter)
        .exceptionHandler(myWebExceptionHandler)
        .build();
```

Đây là snippets với objects đã có; cần imports của `HttpHandler` và `WebHttpHandlerBuilder`. Bản manual không tự khởi động HTTP server. `WebTestClient.bindToHttpHandler(handler)` hoặc mock `MockServerHttpRequest/Response` có thể kiểm tra pipeline không cần mở TCP port.

Theo Spring 6.1, builder tìm các beans thường dùng:

| Loại | Cách tìm/đăng ký | Vai trò |
| --- | --- | --- |
| `WebHandler` | Thường bean tên `webHandler` | Target xử lý request; thường DispatcherHandler |
| `WebFilter` | Beans theo type/ordering | Cross-cutting interception |
| `WebExceptionHandler` | Beans theo type/ordering | Errors chưa được xử lý |
| `WebSessionManager` | Optional bean tên chuẩn | WebSession |
| `ServerCodecConfigurer` | Optional bean tên chuẩn | Form/multipart, codec integration |
| `LocaleContextResolver` | Optional bean tên chuẩn | Locale |
| `ForwardedHeaderTransformer` | Optional bean tên chuẩn | Trust-aware proxy forwarded headers |
| HTTP decorators/observation | Theo phiên bản/config | Observability hoặc wrapper |

**Không tự tạo thêm bean `webHandler` trong ứng dụng Boot REST chỉ vì muốn gắn filter.** Nó có thể thay DispatcherHandler hoặc tạo bean conflict. Dùng `WebFilter`/`WebExceptionHandler` beans là cách đúng để mở rộng phần lớn use cases.

### Ordering của exception handlers

Khi có nhiều `WebExceptionHandler`, order xác định ai được cơ hội xử lý trước. Một handler có thể xử lý custom exception rồi complete; handler kế tiếp không cần nhận nữa. Nếu không nhận diện lỗi, nó phải `Mono.error(ex)` để downstream error chain khác có thể xử lý.

Spring WebFlux cung cấp `ResponseStatusExceptionHandler` và `WebFluxResponseStatusExceptionHandler`. Spring Boot có error handler riêng; thứ tự thực tế của default/custom handlers phải được kiểm chứng theo app. **Không assume tất cả `ResponseStatusException` đều đi qua custom WebExceptionHandler** nếu annotated advice đã xử lý sớm hơn.

## 11. Response commit và giới hạn error handling

Một response thường có các giai đoạn khái niệm:
1. Đặt HTTP status/headers.
2. Chuẩn bị response body publisher.
3. Commit headers và bắt đầu ghi body.
4. Ghi dữ liệu từng phần (có thể streaming).
5. Complete hoặc fail/cancel.

`exchange.getResponse().isCommitted()` cho biết response đã committed ở thời điểm kiểm tra. Sau commit, không thể đảm bảo đổi status/header hoặc bắt đầu JSON error response mới.

### beforeCommit hook

```java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .set("X-Before-Commit", "yes");
    return Mono.empty();
});

return chain.filter(exchange);
```

Đây là snippet trong WebFilter. `beforeCommit` callback được gọi trước commit khi response lifecycle đi đến đó. Đừng gọi blocking database/HTTP sync bên trong callback, và đừng đăng ký callback quá muộn. Khi side effect phụ thuộc subscription, hãy bảo đảm code trả về Publisher được thực thi đúng theo API, không thao tác ngoài chain.

### Lỗi sau partial write

Ví dụ streaming CSV:

```text
HTTP/1.1 200 OK
Content-Type: text/csv

id,name
1,Lan
2,Minh
[Flux<DataBuffer> error]
```

Client đã nhận headers và một phần body. WebExceptionHandler thường không thể biến response thành `500 application/problem+json` nguyên vẹn nữa. Thiết kế streaming protocol phải quy định broken streams, retries, checksums hoặc error events (SSE) khi phù hợp. Đừng nuốt error rồi coi CSV đã thành công.

### ResponseStatusException và @ExceptionHandler

Ở annotated controllers, `@ExceptionHandler`/`@RestControllerAdvice` có thể map lỗi nghiệp vụ thành HTTP response **trước khi** lỗi ra tầng WebExceptionHandler. Với functional routes, handler/filter có thể trả `ServerResponse` lỗi tường minh. Do đó hai error mechanisms bổ sung nhau chứ không có luật "WebExceptionHandler luôn luôn chạy với mọi exception".

## 12. Security, CORS và filter order

Spring Security WebFlux dùng các reactive filters/`SecurityWebFilterChain` để authentication/authorization. Vì vậy các request bảo vệ bởi security chain phải được xác thực trước khi business xử lý. Custom WebFilter thường **không nên** tự giải mã bearer token, suy diễn user qua `X-User`, hoặc implement quyền admin bằng path string.

### Không dùng header client làm quyền

```java
// PHẢN VÍ DỤ: client có thể tự gửi X-Role: ADMIN.
if ("ADMIN".equals(exchange.getRequest()
        .getHeaders().getFirst("X-Role"))) {
    grantAccess();
}
```

Đây là snippet không an toàn, `grantAccess` giả định. Encode/validate header không thay chữ ký, token verification hoặc role/tenant checks. Dùng Spring Security và service-level ACL/authorization checks thay thế.

### CORS không phải authentication

Browser `OPTIONS` preflight có thể đến trước request chính và thường không có credentials. Khi Security chặn preflight trước CORS processing, app có thể xuất hiện lỗi CORS dù endpoint thật hoạt động. Sử dụng Spring WebFlux CORS config/`CorsWebFilter` và tích hợp Spring Security theo tài liệu, đảm bảo origin/method/header/credentials phù hợp. Không thêm `Access-Control-Allow-Origin: *` vào mọi response có cookies.

### Forwarded headers/Host

`Forwarded`/`X-Forwarded-Host`/`X-Forwarded-Proto` có thể bị spoof nếu proxy không sanitize. Khi filter dựng redirect hoặc absolute URL từ request host chưa tin, nguy cơ host header poisoning/phishing/cache poisoning. Proxy tin cậy cần xóa incoming forwarded headers và set canonical values; ứng dụng cần trust model hoặc cấu hình canonical public origin.

### CSRF và session

Với session-cookie auth, POST/PATCH/DELETE WebFlux vẫn có CSRF risk. Không tắt CSRF chỉ vì "API reactive" hoặc muốn curl test nhanh. `WebSession` không tự biến request thành authenticated; session handling và auth policy phải rõ ràng.

## 13. Dự án Spring Boot WebFlux chạy được

Ta xây một app demo:

- `GET /api/demo/hello/{name}`: controller đọc exchange attributes từ filter.
- `GET /api/demo/async`: trả Mono phát kết quả sau một khoảng nhỏ.
- `GET /api/demo/from-controller-error`: tạo lỗi `DemoFailure` từ handler, được custom WebExceptionHandler map thành 503 JSON.
- `GET /api/demo/from-filter-error`: filter bên trong tạo cùng loại lỗi, custom WebExceptionHandler cũng xử lý.
- `GET /api/demo/blocked`: inner filter chủ động short-circuit 429, **không có controller method**, chứng minh filter có thể tự hoàn tất request.
- Hai WebFilters với thứ tự `@Order(-20)` và `@Order(-10)`.
- Một WebExceptionHandler với order `@Order(-2)` để nhận `DemoFailure` trước một số default Boot handlers.
- WebTestClient tests qua embedded server và một low-level mock chain test.

**Giới hạn demo:** Không có authentication, database hay high-load benchmark. JSON error code là chuỗi cố định từ server để tránh injection. Các chính sách rate limit chỉ minh họa bằng một path cố định, **không phải thuật toán rate limit production**.

### 13.1. Cấu trúc project

```text
webflux-filter-demo/
├── pom.xml
└── src/
    ├── main/java/demo/filters/
    │   ├── FilterDemoApplication.java
    │   ├── DemoFailure.java
    │   ├── OuterMarkerFilter.java
    │   ├── InnerPolicyFilter.java
    │   ├── DemoErrorHandler.java
    │   └── DemoController.java
    └── test/java/demo/filters/
        ├── DemoWebFluxTest.java
        └── LowLevelChainTest.java
```

### 13.2. Maven pom.xml

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
    <artifactId>webflux-filter-demo</artifactId>
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

Chỉ thêm `starter-webflux`, **không thêm `starter-web`**, để Boot khởi động reactive WebFlux app thông thường. Khi cả starter-web và starter-webflux cùng trên classpath, Boot thường chọn Servlet MVC trừ khi được cấu hình rõ; đừng kiểm tra một app MVC rồi gọi đó là WebFlux.

### 13.3. Boot application

**`src/main/java/demo/filters/FilterDemoApplication.java`**

```java
package demo.filters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }
}
```

### 13.4. Exception class do ứng dụng sở hữu

**`src/main/java/demo/filters/DemoFailure.java`**

```java
package demo.filters;

public final class DemoFailure extends RuntimeException {
    public DemoFailure(String message) {
        super(message);
    }
}
```

Không dùng `IllegalArgumentException` cho tất cả lỗi vì một IllegalArgumentException có thể đại diện bug lập trình chứ không phải business/HTTP 4xx/5xx cụ thể. Ở đây `DemoFailure` được intentionally mapped thành 503 Service Unavailable.

### 13.5. Outer WebFilter: attributes và header

**`src/main/java/demo/filters/OuterMarkerFilter.java`**

```java
package demo.filters;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-20)
public class OuterMarkerFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest().getPath().value();
        if (!path.startsWith("/api/demo/")) {
            return chain.filter(exchange);
        }

        exchange.getAttributes().put(
                "demo.marker", "outer-filter");
        exchange.getResponse().getHeaders()
                .set("X-Demo-Outer", "visited");

        return chain.filter(exchange);
    }
}
```

Filter này:
- Chỉ thao tác với request paths dưới `/api/demo/`.
- Thêm attribute nội bộ `demo.marker`.
- Thêm response header `X-Demo-Outer` **trước khi** body commit.
- Gọi `chain.filter(exchange)` đúng một lần.
- Không đọc body, không truy cập network/DB và không tạo thread mới.
- Không phụ thuộc vào HTTP handler style: annotated/functional endpoints nếu nằm dưới exchange chain đều có thể được filter.

### 13.6. Inner WebFilter: short-circuit hoặc error signal

**`src/main/java/demo/filters/InnerPolicyFilter.java`**

```java
package demo.filters;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-10)
public class InnerPolicyFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest().getPath().value();
        if (!path.startsWith("/api/demo/")) {
            return chain.filter(exchange);
        }

        exchange.getResponse().getHeaders()
                .set("X-Demo-Inner", "visited");

        if (path.equals("/api/demo/blocked")) {
            exchange.getResponse()
                    .setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
            return exchange.getResponse().setComplete();
        }

        if (path.equals("/api/demo/from-filter-error")) {
            return Mono.error(new DemoFailure("filter-failed"));
        }

        return chain.filter(exchange);
    }
}
```

Nhánh `blocked` cố tình không có controller method. Client vẫn nhận `429 Too Many Requests` vì filter **tự** đặt status và complete; không cần target handler. Nhánh `from-filter-error` trả error publisher. Tầng WebExceptionHandler ở bên ngoài có thể map nó thành HTTP 503.

Quan trọng:
- Đây **không phải** rate limiting bằng key/bucket thật; path cố định chỉ chứng minh short-circuit.
- Không bắt/tự rewrite response đã committed.
- Không tự subscribe.
- Nếu app sau này dùng Spring Security, policy phải được xem lại theo reactive security chain ordering; demo không có Spring Security dependency.

### 13.7. Custom WebExceptionHandler: chỉ xử lý DemoFailure

**`src/main/java/demo/filters/DemoErrorHandler.java`**

```java
package demo.filters;

import java.nio.charset.StandardCharsets;

import org.springframework.core.annotation.Order;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebExceptionHandler;

import reactor.core.publisher.Mono;

@Component
@Order(-2)
public class DemoErrorHandler implements WebExceptionHandler {

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange,
            Throwable error) {

        if (!(error instanceof DemoFailure)) {
            return Mono.error(error);
        }

        if (exchange.getResponse().isCommitted()) {
            return Mono.error(error);
        }

        exchange.getResponse()
                .setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        exchange.getResponse().getHeaders()
                .setContentType(MediaType.APPLICATION_JSON);

        // JSON cố định, không nhúng nội dung exception.
        byte[] data = "{\"code\":\"demo_unavailable\"}"
                .getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = exchange.getResponse()
                .bufferFactory().wrap(data);

        return exchange.getResponse()
                .writeWith(Mono.just(buffer));
    }
}
```

**Tại sao map 503 và body cố định?**

- `DemoFailure` là một error type đã biết, policy cụ thể.
- Không để raw exception message đi thẳng vào JSON vì có thể chứa internal details.
- `WebExceptionHandler` là low-level WebFlux component: viết trực tiếp qua `ServerHttpResponse`, không giả định Jackson sẽ serialize `ApiError` cho mình.
- `isCommitted` được kiểm tra trước status/body. Kiểm tra vẫn không đảm bảo không có race nếu response được commit đồng thời; với async streaming phải có policy riêng.
- `@Order(-2)` minh họa việc tham gia error handler ordering. Trong app Boot thực, audit toàn chain/default handlers và viết integration tests; **đừng dựa chỉ vào số order như bảo chứng trong mọi Spring phiên bản**.
- Với lỗi khác, trả `Mono.error(error)` để default Spring Boot/WebFlux error mechanisms có cơ hội xử lý.

### 13.8. Controller dùng attribute và reactive publisher

**`src/main/java/demo/filters/DemoController.java`**

```java
package demo.filters;

import java.time.Duration;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/demo")
public class DemoController {

    @GetMapping("/hello/{name}")
    public Mono<Map<String, String>> hello(
            @PathVariable String name,
            ServerWebExchange exchange) {

        String marker = exchange.getAttributeOrDefault(
                "demo.marker", "missing");

        return Mono.just(Map.of(
                "name", name,
                "marker", marker));
    }

    @GetMapping("/async")
    public Mono<Map<String, String>> async() {
        return Mono.delay(Duration.ofMillis(20))
                .map(ignored -> Map.of("status", "ready"));
    }

    @GetMapping("/from-controller-error")
    public Mono<String> controllerError() {
        return Mono.error(new DemoFailure("controller-failed"));
    }
}
```

**Kết quả học tập từ demo:**
- Cùng một `ServerWebExchange` đi qua WebFilter và controller; attribute `demo.marker` đọc lại được.
- `Mono.delay` dùng scheduler phát signal trong tương lai thay vì `Thread.sleep` trên event loop.
- Controller `Mono.error(DemoFailure)` cho thấy lỗi từ handler đi qua reactive error chain.
- Không có endpoint controller cho `/blocked` và `/from-filter-error`; chúng được xử lý hoàn toàn ở filter/error-handler tiers.
- Không giữ exchange vào bean field, không tự tạo request-specific mutable state trong singleton.

## 14. Chạy bằng Maven và curl

Tại thư mục `webflux-filter-demo`, cài JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Đây là **hai lệnh tuần tự**. Spring Boot mặc định lắng nghe `localhost:8080` trừ khi port/profile khác đã được cấu hình.

### 14.1. Request thành công

```bash
curl -i 'http://localhost:8080/api/demo/hello/Lan'
```

Các phần đáng chú ý:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Demo-Outer: visited
X-Demo-Inner: visited

{"name":"Lan","marker":"outer-filter"}
```

JSON key order không phải contract; nó phụ thuộc Jackson Map serialization, không assert nguyên chuỗi body theo thứ tự.

### 14.2. Async endpoint

```bash
curl -i 'http://localhost:8080/api/demo/async'
```

Dự kiến HTTP 200, có cả hai headers từ filters, JSON:

```json
{"status":"ready"}
```

Việc dùng Mono.delay không chứng minh event-loop code của toàn app luôn non-blocking; project chỉ có publisher minh họa.

### 14.3. Filter tự short-circuit

```bash
curl -i 'http://localhost:8080/api/demo/blocked'
```

Dự kiến:

```http
HTTP/1.1 429 Too Many Requests
X-Demo-Outer: visited
X-Demo-Inner: visited
```

Body rỗng vì `setComplete()` không cung cấp JSON. Không có controller mapping cho URL này mà vẫn trả 429 — chính `InnerPolicyFilter` đã hoàn thành exchange.

### 14.4. Lỗi từ filter và controller cùng đi tới exception handler

```bash
curl -i 'http://localhost:8080/api/demo/from-filter-error'
curl -i 'http://localhost:8080/api/demo/from-controller-error'
```

Cả hai dự kiến:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
X-Demo-Outer: visited
X-Demo-Inner: visited

{"code":"demo_unavailable"}
```

Đây là contract do **custom `WebExceptionHandler`** cung cấp cho `DemoFailure`. Nếu một exception đã được annotated `@ExceptionHandler` xử lý thành response trước đó, WebExceptionHandler không bắt buộc nhận nó. Cũng không giả định default Boot error response có cùng schema.

## 15. WebTestClient integration tests với HTTP server thật

**`src/test/java/demo/filters/DemoWebFluxTest.java`**

```java
package demo.filters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class DemoWebFluxTest {

    @Autowired
    WebTestClient client;

    @Test
    void bothFiltersRunBeforeAnnotatedController() {
        client.get().uri("/api/demo/hello/Lan")
              .exchange()
              .expectStatus().isOk()
              .expectHeader().valueEquals(
                      "X-Demo-Outer", "visited")
              .expectHeader().valueEquals(
                      "X-Demo-Inner", "visited")
              .expectBody()
              .jsonPath("$.marker").isEqualTo("outer-filter")
              .jsonPath("$.name").isEqualTo("Lan");
    }

    @Test
    void asyncBodyFinishes() {
        client.get().uri("/api/demo/async")
              .exchange()
              .expectStatus().isOk()
              .expectBody()
              .jsonPath("$.status").isEqualTo("ready");
    }

    @Test
    void filterCanCompleteRequestWithoutController() {
        client.get().uri("/api/demo/blocked")
              .exchange()
              .expectStatus().isEqualTo(429)
              .expectHeader().valueEquals(
                      "X-Demo-Inner", "visited");
    }

    @Test
    void errorFromFilterGoesToWebExceptionHandler() {
        client.get().uri("/api/demo/from-filter-error")
              .exchange()
              .expectStatus().isEqualTo(503)
              .expectBody()
              .jsonPath("$.code")
                  .isEqualTo("demo_unavailable");
    }

    @Test
    void errorFromControllerAlsoReachesHandler() {
        client.get().uri("/api/demo/from-controller-error")
              .exchange()
              .expectStatus().isEqualTo(503)
              .expectBody()
              .jsonPath("$.code")
                  .isEqualTo("demo_unavailable");
    }
}
```

Các tests chạy với embedded server `RANDOM_PORT`, gửi HTTP thông qua `WebTestClient`. Có **5 test methods**; chúng kiểm tra cả success/short-circuit/error flow, không chỉ gọi trực tiếp Java controller.

Điều tests **chưa** chứng minh:
- Spring Security authentication/CSRF rules (demo chưa thêm Security).
- Proxy/ingress forwarded headers đúng production.
- Backpressure và performance khi hàng nghìn slow clients.
- Lỗi socket sau khi response đã stream một phần.
- HTTP status/body đồng nhất giữa mọi Spring Boot versions.

## 16. Low-level unit test cho WebFilterChain và WebExceptionHandler

Để quan sát cách builder lắp tầng web khi **không có controller**, dùng một `WebHandler` custom với filter/error handler manual. Không cần khởi động Netty server.

**`src/test/java/demo/filters/LowLevelChainTest.java`**

```java
package demo.filters;

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

class LowLevelChainTest {

    @Test
    void manualChainRunsFilterThenWebHandler() {
        WebHandler target = exchange -> {
            String marker = exchange.getAttributeOrDefault(
                    "marker", "missing");

            exchange.getResponse()
                    .setStatusCode(HttpStatus.OK);
            exchange.getResponse().getHeaders()
                    .setContentType(MediaType.TEXT_PLAIN);

            DataBuffer buffer = exchange.getResponse()
                    .bufferFactory()
                    .wrap(marker.getBytes(StandardCharsets.UTF_8));

            return exchange.getResponse()
                    .writeWith(Mono.just(buffer));
        };

        WebFilter filter = (exchange, chain) -> {
            exchange.getAttributes()
                    .put("marker", "filter-was-here");
            return chain.filter(exchange);
        };

        HttpHandler handler = WebHttpHandlerBuilder
                .webHandler(target)
                .filter(filter)
                .build();

        MockServerHttpRequest request =
                MockServerHttpRequest.get("/raw").build();
        MockServerHttpResponse response =
                new MockServerHttpResponse();

        handler.handle(request, response)
                .block(Duration.ofSeconds(2));

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("filter-was-here",
                response.getBodyAsString()
                        .block(Duration.ofSeconds(2)));
    }

    @Test
    void manualExceptionHandlerCanCatchFilterError() {
        WebHandler target = exchange ->
                exchange.getResponse().setComplete();

        WebFilter broken = (exchange, chain) ->
                Mono.error(new DemoFailure("expected"));

        HttpHandler handler = WebHttpHandlerBuilder
                .webHandler(target)
                .filter(broken)
                .exceptionHandler(new DemoErrorHandler())
                .build();

        MockServerHttpRequest request =
                MockServerHttpRequest.get("/raw-error").build();
        MockServerHttpResponse response =
                new MockServerHttpResponse();

        handler.handle(request, response)
                .block(Duration.ofSeconds(2));

        assertEquals(HttpStatus.SERVICE_UNAVAILABLE,
                response.getStatusCode());
        assertEquals("{\"code\":\"demo_unavailable\"}",
                response.getBodyAsString()
                        .block(Duration.ofSeconds(2)));
    }
}
```

Test class có **2 test methods**. Cộng với 5 tests ở mục 15 là **7 test methods**. Nếu project được tạo đúng và `mvn test` thực thi tất cả thành công, Maven exit code là 0 và thường thấy tổng tương tự `Tests run: 7, Failures: 0, Errors: 0, Skipped: 0` (cách báo cáo theo plugin/test runners có thể khác).

**Vì sao `block()` có mặt trong test?** Đây là unit test chạy ngoài event loop, cần đợi completion của một Mono trên mock exchange để assert body; việc blocking **chỉ phục vụ test**. Trong WebFilter/controller production không có `block()` hoặc `subscribe()` thủ công.

**Giới hạn test:** Lớp mock HTTP không tái hiện mọi đặc điểm socket/I/O, timeouts và WebFlux controller metadata. Test manual chain bổ sung cho integration tests, không thay thế chúng.

## 17. Viết custom WebFilter hiệu quả và an toàn

### 17.1. Không đọc request body hai lần

`ServerHttpRequest.getBody()` là `Flux<DataBuffer>`, thường đại diện one-shot network stream. Cách sai:

```java
// PHẢN VÍ DỤ: tự subscribe raw body và để handler đọc lần nữa.
exchange.getRequest().getBody()
        .subscribe(buffer -> logRaw(buffer));
return chain.filter(exchange);
```

Đây là pseudocode vì `logRaw` chưa có. Nó có thể:
- Tiêu thụ body trước controller decoder, khiến `@RequestBody` nhận dữ liệu rỗng/lỗi.
- Tạo hai subscriptions cạnh tranh.
- Làm lộ password/token/PII trong logs.
- Rò rỉ pooled DataBuffer nếu không release.
- Mất backpressure/cancellation của outer request pipeline.

Nếu thực sự cần audit body, ưu tiên instrumentation được framework hỗ trợ, hoặc xây decorator/buffer policy có **giới hạn bytes**, bảo toàn backpressure và release ownership. Đừng mặc định một WebFilter được phép log mọi HTTP body.

### 17.2. Avoid blocking I/O trong filter

```java
// PHẢN VÍ DỤ: blocking JDBC trên WebFlux event loop.
User user = jdbcRepository.findById(id);
return chain.filter(exchange);
```

Đây là snippet minh họa, `jdbcRepository`/`id` do ứng dụng giả định. Chữ ký `Mono<Void>` không khiến đoạn JDBC đồng bộ thành non-blocking.

Nếu cần thư viện blocking tạm thời:

```java
return Mono.fromCallable(() -> blockingPolicyService.evaluate(id))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(allowed -> {
            if (!allowed) {
                exchange.getResponse()
                        .setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }
            return chain.filter(exchange);
        });
```

Đây là snippet có service/id imports chưa định nghĩa. `boundedElastic` **offload việc block sang bounded thread pool**, không biến driver thành non-blocking. Bảo vệ pool size, queue, downstream timeout và transaction/context. Với hệ thống reactive thực sự, ưu tiên auth/policy lookup dùng driver/client non-blocking.

### 17.3. Không giữ request/exchange vào singleton fields

`@Component` WebFilter thường singleton và phục vụ nhiều requests đồng thời. Không làm:

```java
private ServerWebExchange currentExchange;
```

rồi gán trong filter để dùng về sau. Request A và B có thể ghi đè state, gây rò rỉ dữ liệu và giữ request resources sau completion. Dùng biến local, exchange attributes, Reactor Context và request-specific structures cần cleanup.

### 17.4. Reactive Context và MDC

Dữ liệu trace/user/security không nên dựa chỉ vào custom `ThreadLocal` vì reactive work có thể chuyển scheduler. Sử dụng Reactor Context/context propagation của Spring/Micrometer/Spring Security; nếu map với MDC, luôn restore/clear phù hợp. `exchange.getAttributes()` có thể dùng để pass một marker nội bộ nhưng không thay full distributed tracing context.

### 17.5. Metrics cardinality

Một filter muốn ghi request count theo path không nên dùng raw `/users/1000001`, `/users/1000002` làm mỗi tag mới. Nên dùng **route template** `/users/{id}` khi sẵn có và thận trọng với thời điểm route mapping được resolve. Không log query có access tokens hoặc values mang PII.

### 17.6. Cancellation

`doFinally(signalType -> ...)` nhận `CANCEL` khi subscriber cancel. Client disconnect thường dẫn tới cancellation ở một số cấp reactive pipeline, nhưng **không mọi** kiểu network failure đều quan sát y hệt `CANCEL`. Hãy cleanup resources trong finally/dispose/usingWhen đúng contract, không chỉ `doOnSuccess`.

## 18. CORS, tracing và auth: nên gắn ở đâu?

| Nhu cầu | Vị trí phù hợp | Không nên làm |
| --- | --- | --- |
| Authentication/authorization | Spring Security reactive `SecurityWebFilterChain` + service ACL | Tự tin `X-Role` client |
| CORS | Spring WebFlux CORS config/`CorsWebFilter` đúng thứ tự với security | Wildcard allow-origin + credentials |
| Correlation/trace | Observation/Micrometer + Reactor Context | Copy raw `ThreadLocal` tùy tiện |
| Request header policy | WebFilter có phạm vi rõ | Set sau commit |
| Rate limiting | Gateway/server-side shared policy với key tin cậy | Short-circuit dựa trên user-supplied "admin" header |
| Domain errors | Controller advice/functional handler mapping tùy scope | WebExceptionHandler bắt mọi Exception rồi trả 400 |
| Infrastructure errors | WebExceptionHandler có thứ tự và fallback đúng | Bỏ qua error khi response đã committed |
| Request body logging | Approved redacted bounded instrumentation | subscribe body trước converter |
| Logging status/latency | Observation hoặc WebFilter có cleanup | High-cardinality tags, log secrets |
| HTTP response transform | Codec/result handler hoặc decorater phù hợp | Edit headers sau commit |

### Vì sao không dùng một filter cho tất cả?

Một filter ôm auth, CORS, multipart parsing, cache, tracing, error serialization và metrics sẽ:
- Khó kiểm soát order và trust boundaries.
- Dễ tạo hai subscriptions/đọc body lặp.
- Cản trở unit/integration tests.
- Dễ nuốt exceptions hoặc làm sai status.
- Phức tạp khi migrate Spring Security/Boot phiên bản.

Dùng filter nhỏ, trách nhiệm rõ, composition qua Spring container và test các hợp đồng.

## 19. Phân tích sự khác nhau giữa 401/403/404/429 và lỗi publisher

**HTTP 401 Unauthorized**: client chưa được xác thực đúng, thường do authentication entry point ở Spring Security xử lý, có thể cần `WWW-Authenticate` theo scheme.

**HTTP 403 Forbidden**: client có identity nhưng không đủ quyền (hoặc CSRF rules), thường do authorization policy.

**HTTP 404 Not Found**: không có route/resource phù hợp; có thể là một response hoàn toàn bình thường, Mono complete thành công.

**HTTP 429 Too Many Requests**: policy rate limit chủ động short-circuit; có thể thêm `Retry-After` nếu có semantics rõ.

**HTTP 503 Service Unavailable**: backend/dependency tạm không sẵn sàng; trong demo do `DemoFailure` custom exception handler trả về.

**Reactive error signal**: publisher thất bại. Signal này **không tự xác định status**; handler/error mapping quyết định status trước khi response commit.

Một ứng dụng nên phân biệt:
- HTTP response status metrics.
- Exceptions/error signals.
- Client cancellation.
- Downstream 5xx errors từ WebClient (có thể là ordinary ResponseEntity nếu dùng exchangeToMono và xử lý status chủ động).
- Body streaming failures sau commit.

Không coi mọi 4xx là Java exception và không coi mọi Mono.error tự động thành 500 JSON cùng schema.

## 20. WebExceptionHandler, @ControllerAdvice và functional router error handling

Cùng một app WebFlux có thể kết hợp:
- Annotated controller `@ExceptionHandler`/`@RestControllerAdvice`.
- Functional router `HandlerFilterFunction` hoặc explicit `ServerResponse` cho lỗi domain.
- Outer `WebExceptionHandler` cho lỗi còn thoát ra hạ tầng WebHandler chain.
- Spring Boot `ErrorWebExceptionHandler` mặc định cho các exceptions khác.

**Thứ tự logic:** nếu exception đã được một tầng bên trong chuyển thành HTTP response, tầng bên ngoài thường chỉ nhìn completion bình thường; nó không có lý do nhận cùng exception lần nữa. Nếu tầng bên trong để error propagate, WebExceptionHandler có thể nhận. Nếu đã commit một phần response, việc biến đổi body/status có giới hạn.

### Không nuốt lỗi không nhận diện

```java
if (!(error instanceof MyExpectedError)) {
    return Mono.error(error);
}
```

Dòng này có vai trò quan trọng trong custom WebExceptionHandler: **để những handlers/fallbacks khác xử lý**. Nếu luôn trả `Mono.empty()` cho mọi exception, request có thể trông như thành công hoặc chứa response body dang dở mà không có status thích hợp.

### Không lộ nội dung Throwable

`error.getMessage()` có thể chứa secrets, SQL fragments, internal hostnames hoặc stack details. Error response ra public cần code/messages đã sanitize. Logs nội bộ dùng trace ID, security-safe context và structured logging, tránh dump auth headers/raw request body.

## 21. Debugging checklist

Khi filters hoặc custom exception handling hoạt động không như kỳ vọng:

1. **Xác định đúng stack**: Boot có đang chạy WebFlux reactive hay vô tình MVC do starter-web?
2. Xác nhận imports `org.springframework.web.server.WebFilter`/`WebFilterChain`/`WebExceptionHandler`, không phải Servlet Filter.
3. Kiểm tra @Component/@Bean được component scan, không tạo hai registrations.
4. Xem order qua `@Order`/`Ordered`, đặc biệt khi có Spring Security/CORS.
5. Đặt marker/header trong hai filters để chứng minh request đi qua thứ tự mong muốn.
6. Kiểm tra filter có **return** `chain.filter(exchange)` đúng một lần không.
7. Với request 429/403, xác định filter đã short-circuit và target controller không gọi.
8. Với error, kiểm tra `Mono.error` có propagate hay đã được `onErrorResume` xử lý.
9. Kiểm tra `@ControllerAdvice` có xử lý trước WebExceptionHandler hay không.
10. Xem `exchange.getResponse().isCommitted()` khi custom handler không thay status.
11. Nếu body trống, tìm code subscribe/read `getBody()` từ một WebFilter.
12. Nếu app chậm, tìm `block()`/JDBC sync trên event loops và queue overload.
13. Nếu response headers không có, kiểm tra thời điểm commit hoặc filter scope.
14. Nếu 404 dù route tồn tại, xem predicate/method/path, handler mapping và prefix.
15. Nếu CORS preflight bị 401/403, xem WebFlux CORS/Security order và OPTIONS policy.
16. Nếu memory tăng, xem buffers, sessions, long-lived publishers và cancellation cleanup.
17. Với forwarded headers, kiểm tra proxy sanitize/trust policy tránh Host injection.
18. Test app với WebTestClient và sau đó qua reverse proxy/runtime giống production.

## 22. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân | Sửa thế nào |
| --- | --- | --- |
| Không thấy filter chạy | Import nhầm Servlet filter, bean không scan, sai path scope | Dùng đúng WebFlux WebFilter và xác minh bean |
| Filter bị gọi lặp | Tự subscribe chain hoặc đăng ký hai lần | Return chain duy nhất, đăng ký một bean |
| Controller không chạy | Filter quên `chain.filter(exchange)` hoặc short-circuit | Xem nhánh return, test 429 intentional |
| WebExceptionHandler không bắt lỗi | Error đã được advice xử lý hoặc detached subscription | Kiểm tra propagation, bỏ manual subscribe |
| WebExceptionHandler chạy nhưng không đổi status | Response đã committed | Error handling sớm; streaming error policy |
| HTTP 404 nhưng `doOnError` không chạy | 404 là response bình thường | Đọc response status, không chỉ error signal |
| `Mono<Void>` đã return mà request đứng | Publisher không complete/never callback | Kiểm tra subscription, timeouts và producer |
| CPU cao | Blocking database/call trong event loop | Non-blocking client hoặc bounded offload |
| Request body bị mất | WebFilter đọc one-shot body trước decoder | Không double-read; decorator đúng |
| Response bị ghi hai lần | Filter và handler cùng write/subscribe | Một chain một writer theo policy |
| Error body lộ SQL exception | Trả raw Throwable message | Sanitized API errors |
| `@Order` làm mất auth | Đặt custom filter trước/ngoài policy không kiểm chứng | Spring Security integration + tests |
| Filter không nhìn thấy principal | Chưa authenticated hoặc Mono empty | Reactive SecurityContext/Principal |
| Mất trace ID | Dùng ThreadLocal ngoài Reactor Context | Supported context propagation |
| Session creation nhiều | Filter gọi/ghi session không cần thiết | Chỉ dùng session khi thực sự cần |
| Header mất | Đặt sau commit | Set trước hoặc beforeCommit |
| CORS lỗi | Security chặn OPTIONS/preflight | Config CORS đúng thứ tự |
| Mutable field lộ data user | Singleton filter giữ state request | Dùng local/exchange attributes |
| Netty buffer leak | Không release retained DataBuffer | DataBufferUtils.release đúng ownership |
| Retry gây duplicate POST | Retry publisher từ filter khi endpoint có side effect | Dùng idempotency contract, tránh retry bừa |
| Unexpected 200 empty body | Nuốt error bằng `Mono.empty()` hoặc setComplete thiếu status | Map error/status rõ |
| Slow client làm memory tăng | Buffer không giới hạn, thiếu backpressure | Bounded buffering, cancellation, observe |
| WebFilter khác GatewayFilter | Nhầm Spring Cloud Gateway-specific API | Phân biệt WebFlux vs Gateway |
| Test pass nhưng production error status khác | Default Boot handler/version khác, proxy/commit | Integration test on actual stack |

## 23. Checklist triển khai production

- [ ] Đúng `spring-boot-starter-webflux` và reactive application context.
- [ ] WebFilter beans được scan, order rõ, không duplicate.
- [ ] Mỗi nhánh hoặc **return chain once** hoặc **short-circuit + response completion**.
- [ ] Không gọi `block()`/`subscribe()` thủ công trên event-loop request pipeline.
- [ ] Không log body/Authorization/Cookie hoặc request ID nhạy cảm.
- [ ] Attributes namespaced; không lưu request-specific data vào singleton fields.
- [ ] Header/status được set trước response commit.
- [ ] WebExceptionHandler chỉ bắt error loại biết, giữ fallback cho error khác.
- [ ] Error JSON không leak raw Throwable và status phù hợp.
- [ ] Streaming errors và cancellation có cleanup riêng.
- [ ] SecurityWebFilterChain xử lý authentication/authorization đúng.
- [ ] CORS/preflight/CSRF/session policy đúng khi có credentials.
- [ ] Hạn chế forwarded headers và Host trust boundary.
- [ ] Giới hạn body/multipart, pooled DataBuffers và backpressure.
- [ ] Metrics theo route template, không tạo high-cardinality tags.
- [ ] WebTestClient kiểm chứng success, block, filter error và handler error.
- [ ] Low-level tests dành cho custom infrastructure, không thay integration tests.
- [ ] Downstream timeouts, rate limiting, retries, circuit breaker và observability được thiết kế riêng.

## 24. Bài tập tự kiểm tra

1. `WebFilter.filter` nhận đối số nào? Trả kiểu gì?
2. `WebFilterChain.filter(exchange)` đại diện cho phần xử lý nào?
3. Khi nào một filter không nên gọi `chain.filter`?
4. Khác biệt giữa HTTP 404 response và `Mono.error` là gì?
5. Vì sao WebExceptionHandler không thể luôn trả 500 JSON khi lỗi xuất hiện giữa stream?
6. `@Order(-20)` và `@Order(-10)` ảnh hưởng gì tới nesting chain?
7. Vì sao không tự `subscribe()` trên Mono của chain?
8. `doFinally` khác `doOnError` thế nào?
9. `ServerWebExchange.getAttributes()` khác Reactor Context?
10. `getPrincipal()` là async vì lý do gì?
11. Nếu filter muốn gắn header trước commit, cần làm gì?
12. `WebExceptionHandler` nhận error từ cả WebFilter và WebHandler được không?
13. Khi nào nó không bắt error do controller phát ra?
14. Vì sao custom exception handler nên trả `Mono.error(ex)` cho errors không được nhận diện?
15. Servlet `Filter` và WebFlux `WebFilter` khác API nào?
16. Có nên triển khai authentication từ `X-User` client header trong custom filter?
17. CORS có thay thế quyền truy cập được không?
18. Vì sao raw body publisher thường không được đọc hai lần?
19. `DataBuffer` pooled có thể gây leak ở đâu?
20. Bằng cách nào test WebFilter và custom WebExceptionHandler mà không mở port?
21. Tại sao phải phân biệt `setComplete()` với viết response JSON?
22. `Mono.delay` có chứng minh tất cả nghiệp vụ non-blocking không?
23. Vì sao phải test cancel khi server stream dữ liệu lâu?
24. Khi thêm WebFilter, tại sao không nên tự định nghĩa lại bean `webHandler`?
25. Số lượng HTTP 5xx có luôn bằng số Mono.error signals không?

**Gợi ý:** (1) Exchange + chain, Mono<Void>. (2) Các filters tiếp theo và WebHandler cuối. (3) Khi đã short-circuit hợp lệ. (4) Một cái response status; cái kia error signal. (5) Đã commit/ghi body. (6) Outer/inner theo thứ tự. (7) Runtime subscribe và cần một pipeline. (8) doFinally còn thấy cancellation. (9) Request map vs subscription context. (10) Reactive auth/context services. (11) Đặt sớm hoặc beforeCommit. (12) Có nếu lỗi propagate. (13) Đã được advice/inner handler xử lý. (14) Cho fallback khác xử lý. (15) Reactive Mono và ServerWebExchange vs Servlet doFilter. (16) Không. (17) Không. (18) One-shot network stream. (19) Decorators/caching/subscribe lặp không release. (20) WebHttpHandlerBuilder + mock requests/responses. (21) setComplete không có body. (22) Không. (23) Giải phóng subscriptions/buffers/connections. (24) Dễ thay DispatcherHandler. (25) Không.

## 25. Tài liệu tham khảo

- [Spring Framework — WebFlux Reactive Core: WebHandler API, Filters and Exceptions](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework 6.1 — WebFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebFilter.html)
- [Spring Framework 6.1 — WebFilterChain Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebFilterChain.html)
- [Spring Framework 6.1 — WebExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebExceptionHandler.html)
- [Spring Framework 6.1 — WebHttpHandlerBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/adapter/WebHttpHandlerBuilder.html)
- [Spring Framework 6.1 — DefaultWebFilterChain Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/handler/DefaultWebFilterChain.html)
- [Spring Framework 6.1 — ServerWebExchange Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/ServerWebExchange.html)
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html)
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html)
- [Spring Security — Reactive Web Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)

**Kết luận:** `WebFilter` can thiệp quanh reactive HTTP exchange, `WebFilterChain` tiếp tục các filters và WebHandler đích, còn `WebExceptionHandler` xử lý **error signals chưa được xử lý** ở tầng web khi response vẫn có thể thay đổi. Ba abstraction này giúp tổ chức logging, policy, error handling và observability mà không phụ thuộc việc endpoint dùng annotated controller hay WebFlux.fn. Muốn đúng và an toàn, phải **return một publisher duy nhất**, không tự subscribe/block, kiểm soát order/security, hiểu response commit và body ownership, và test riêng success, short-circuit, errors, cancellation.

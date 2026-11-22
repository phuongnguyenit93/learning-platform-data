# WebFilter áp dụng logic trước và sau filter chain trong Spring WebFlux

## 1. WebFilter là gì?

Spring WebFlux xử lý HTTP request bằng WebHandler reactive. Trước khi request tới handler cuối cùng (thường là DispatcherHandler), request có thể đi qua một chuỗi WebFilter. Mỗi filter có thể đọc request, thêm metadata vào exchange, kiểm tra điều kiện, chặn request hoặc chuyển quyền xử lý cho filter tiếp theo.

`WebFilter` là contract để áp dụng logic xuyên suốt nhiều endpoint, ví dụ:

- Gắn request ID hoặc correlation ID.
- Ghi log thời gian xử lý và kết quả response.
- Đọc principal hoặc session để đưa thông tin vào request context.
- Thêm header chung, áp dụng CORS hoặc chính sách truy cập.
- Đo metrics, tracing, timeout và quan sát lỗi.
- Chặn request sớm khi điều kiện không đạt.

Một WebFilter triển khai method:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
~~~

Hai tham số có vai trò khác nhau:

- `ServerWebExchange` đại diện cho một lần trao đổi HTTP, cung cấp request, response, attributes, session, principal và các thông tin liên quan.
- `WebFilterChain` cho phép filter chuyển request sang filter tiếp theo bằng `chain.filter(exchange)`.

Kết quả `Mono<Void>` biểu diễn quá trình xử lý request/response đã hoàn tất. Filter trả publisher cho WebFlux quản lý; không cần tự subscribe hoặc chờ bằng block.

**Before và after:** code chạy trước lời gọi `chain.filter` là phần trước chain. Các callback gắn vào publisher của chain có thể quan sát lúc chain hoàn tất, phát lỗi hoặc bị hủy. Trong Reactor, phần sau được biểu diễn bằng các operator như `doOnSuccess`, `doOnError`, `doFinally`, `then` và `onErrorResume`.

## 2. Vị trí của WebFilter trong request lifecycle

~~~text
HTTP request
    |
    v
Reactive Web Server
    |
    v
WebHandler / WebHttpHandlerBuilder
    |
    v
WebFilter A
    |
    v
WebFilter B
    |
    v
WebFilter C
    |
    v
DispatcherHandler
    |
    +--> annotated controller
    |
    +--> functional RouterFunction / HandlerFunction
    |
    v
Response được ghi
    |
    v
Filter callbacks quan sát complete/error/cancel
    |
    v
HTTP response hoàn tất
~~~

Filter bao quanh quá trình xử lý request. Nó chạy trước controller hoặc functional handler và có thể quan sát kết quả sau khi publisher của handler kết thúc. Vì vậy WebFilter phù hợp với chính sách áp dụng rộng trên toàn ứng dụng WebFlux.

WebFilter không phải controller và không nên chứa logic domain như tạo đơn hàng hoặc tính giá. Hãy giữ filter ở mức cross-cutting concern: logging, tracing, security, session, CORS, metrics hoặc header.

Spring Boot tự phát hiện bean kiểu `WebFilter` trong application context và đưa chúng vào chuỗi xử lý WebFlux. Có thể dùng `@Order` hoặc implement `Ordered` khi cần xác định thứ tự. Tài liệu Spring Boot Reactive Web Applications và Javadoc WebFilter mô tả contract này.

## 3. WebFilterChain và nguyên tắc gọi chain

~~~java
@Component
public class ExampleWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        // Logic trước filter tiếp theo
        return chain.filter(exchange);
    }
}
~~~

`chain.filter(exchange)` chuyển quyền xử lý cho phần tiếp theo của chuỗi. Phần tiếp theo có thể là WebFilter khác hoặc WebHandler cuối cùng.

| Hành vi | Cách làm | Kết quả |
| --- | --- | --- |
| Cho request đi tiếp | `return chain.filter(exchange)` | Filter tiếp theo và handler được chạy |
| Chặn request | Tạo status/body rồi return publisher hoàn tất | Chain phía sau không được gọi |
| Quan sát kết quả | Gắn operator vào publisher của chain | Ghi nhận success, error hoặc cancel |

Ví dụ chặn request:

~~~java
@Component
public class MaintenanceWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        if (exchange.getRequest().getPath().value().startsWith("/admin")) {
            exchange.getResponse().setStatusCode(
                HttpStatus.SERVICE_UNAVAILABLE);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}
~~~

Request có path bắt đầu bằng `/admin` bị chặn. Filter đặt status 503 và gọi `setComplete()` để hoàn tất response. Vì không gọi `chain.filter`, các filter phía sau và handler không được thực thi.

Trong ứng dụng thật, điều kiện bảo trì nên dựa trên cấu hình hoặc trạng thái hệ thống được quản lý. Với xác thực và phân quyền, ưu tiên Spring Security reactive.

**Không gọi `chain.filter(exchange)` hai lần cho cùng một request.** Việc gọi chain lặp có thể khiến handler chạy nhiều lần, đọc body nhiều lần hoặc thực hiện side effect trùng lặp.

## 4. Logic trước chain

Có thể thực hiện logic trước chain ngay trong filter:

~~~java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    String path = exchange.getRequest().getPath().value();
    log.info("Incoming request: {}", path);

    return chain.filter(exchange);
}
~~~

Nếu muốn bảo đảm side effect chỉ xảy ra khi publisher được subscribe, dùng `Mono.defer`:

~~~java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    return Mono.defer(() -> {
        log.info("Before chain: {} {}",
            exchange.getRequest().getMethod(),
            exchange.getRequest().getURI().getPath());

        return chain.filter(exchange);
    });
}
~~~

`Mono.defer` trì hoãn phần thân cho tới subscription. Cách này hữu ích khi tạo timer, log hoặc lấy giá trị theo từng lần thực thi publisher.

### 4.1. Đo thời gian xử lý

~~~java
return Mono.defer(() -> {
    long startedAt = System.nanoTime();

    return chain.filter(exchange)
        .doFinally(signal -> {
            long elapsedNanos = System.nanoTime() - startedAt;
            log.info("Request finished: signal={}, elapsed={}ms",
                signal, elapsedNanos / 1_000_000);
        });
});
~~~

`System.nanoTime()` thích hợp để đo khoảng thời gian vì nó là đồng hồ monotonic, không dùng để lấy thời điểm lịch. `doFinally` quan sát terminal signal, gồm complete, error và cancel. Không nên dùng phép trừ `System.currentTimeMillis()` để đo thời lượng chính xác vì đồng hồ hệ thống có thể bị điều chỉnh.

## 5. Logic sau chain: success, error và cancel

Với `Mono<Void>`, có ba nhóm terminal signal cần phân biệt:

| Tín hiệu | Ý nghĩa | Operator phù hợp |
| --- | --- | --- |
| Complete | Chain hoàn tất bình thường | `doOnSuccess`, `doOnTerminate`, `then` |
| Error | Chain kết thúc bằng lỗi | `doOnError`, `onErrorResume`, `doFinally` |
| Cancel | Subscription bị hủy | `doOnCancel`, `doFinally` |

### 5.1. Sau khi chain hoàn tất thành công

~~~java
return chain.filter(exchange)
    .doOnSuccess(ignored ->
        log.info("Request completed successfully"));
~~~

`doOnSuccess` chạy khi Mono hoàn tất thành công. Với `Mono<Void>`, giá trị phát ra là `null`; callback không nên dereference tham số.

### 5.2. Khi chain phát lỗi

~~~java
return chain.filter(exchange)
    .doOnError(error ->
        log.error("Request failed", error));
~~~

`doOnError` chỉ quan sát lỗi và để lỗi tiếp tục truyền xuống subscriber. Đây thường là lựa chọn đúng khi chỉ cần logging/metrics và để WebExceptionHandler hoặc Spring Security xử lý lỗi.

Nếu dùng `onErrorResume`, filter có thể chuyển lỗi thành publisher khác:

~~~java
return chain.filter(exchange)
    .onErrorResume(IllegalArgumentException.class, error -> {
        exchange.getResponse().setStatusCode(HttpStatus.BAD_REQUEST);
        return exchange.getResponse().setComplete();
    });
~~~

Chỉ map lỗi mà filter hiểu rõ. Không bắt mọi exception rồi trả 200 hoặc 400; lỗi hạ tầng và bug lập trình cần được xử lý theo chính sách lỗi của ứng dụng.

### 5.3. Khi client hủy request

Client có thể đóng kết nối, timeout hoặc hủy subscription. Khi đó chain có thể nhận cancel thay vì complete/error.

~~~java
return chain.filter(exchange)
    .doOnCancel(() ->
        log.info("Client cancelled request"));
~~~

Cancellation không đồng nghĩa lỗi nghiệp vụ. Có thể ghi nhận để quan sát, nhưng tránh cố ghi error response khi client đã ngắt kết nối.

### 5.4. Kết hợp đầy đủ

~~~java
return Mono.defer(() -> {
    long startedAt = System.nanoTime();
    log.info("Before chain");

    return chain.filter(exchange)
        .doOnSuccess(ignored ->
            log.info("Chain completed"))
        .doOnError(error ->
            log.warn("Chain failed", error))
        .doFinally(signal -> {
            long elapsedMs =
                (System.nanoTime() - startedAt) / 1_000_000;
            log.info("After chain: signal={}, elapsed={}ms",
                signal, elapsedMs);
        });
});
~~~

Log đầu tiên chạy trước chain; `doOnSuccess` quan sát complete; `doOnError` quan sát lỗi; `doFinally` chạy với complete, error hoặc cancel.

Không nhầm `doFinally` với callback chỉ chạy khi thành công. Nếu hành động chỉ được thực hiện sau success, dùng `then` hoặc `doOnSuccess`. Nếu cần cleanup bất kể kết quả, dùng `doFinally` hoặc cơ chế cleanup phù hợp.

## 6. Thứ tự nhiều WebFilter: request đi xuôi, callback quay ngược

Giả sử có ba filter theo thứ tự A, B, C:

~~~text
Request:
A.before
  B.before
    C.before
      Handler
    C.after
  B.after
A.after
~~~

Filter chạy vào theo chain. Khi publisher hoàn tất và callback được gắn trên từng tầng thực thi, phần xử lý sau chain diễn ra khi reactive stack unwind. Vì vậy callback ở filter trong cùng thường quan sát kết quả trước filter ngoài.

~~~java
@Component
@Order(1)
class FirstFilter implements WebFilter {
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        log.info("A before");
        return chain.filter(exchange)
            .doFinally(signal -> log.info("A after"));
    }
}

@Component
@Order(2)
class SecondFilter implements WebFilter {
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        log.info("B before");
        return chain.filter(exchange)
            .doFinally(signal -> log.info("B after"));
    }
}
~~~

Với hai filter này, log đi vào là A trước rồi B. Khi chain kết thúc, callback B chạy rồi A. Đây là mô hình hữu ích để hiểu tracing, transaction scope và thời gian xử lý.

Thứ tự thực tế phụ thuộc cấu hình và cách Spring ghép filter. Hãy khai báo order rõ ràng khi logic phụ thuộc thứ tự; không dựa vào thứ tự phát hiện bean tình cờ.

## 7. @Order và Ordered

Có hai cách khai báo thứ tự.

### 7.1. Dùng @Order

~~~java
@Component
@Order(10)
public class RequestIdWebFilter implements WebFilter {
    // ...
}
~~~

### 7.2. Implement Ordered

~~~java
@Component
public class AuditWebFilter implements WebFilter, Ordered {
    @Override
    public int getOrder() {
        return 20;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {
        return chain.filter(exchange);
    }
}
~~~

Giá trị order nhỏ hơn có độ ưu tiên cao hơn và thường chạy sớm hơn trong request path. `Ordered.HIGHEST_PRECEDENCE` là giá trị ưu tiên cao nhất; `Ordered.LOWEST_PRECEDENCE` là giá trị ưu tiên thấp nhất.

Nếu nhiều filter có cùng order, không nên phụ thuộc vào thứ tự tie-break không được quy định trong cấu hình ứng dụng. Hãy chọn giá trị order riêng khi thứ tự có ý nghĩa.

### 7.3. Tương tác với Spring Boot và Spring Security

Spring Boot có thể đăng ký WebFilter nội bộ như observation hoặc filter của Spring Security. Một số order mặc định thay đổi theo phiên bản Boot và cấu hình. Tài liệu Spring Boot hiện tại ghi nhận `WebFilterChainProxy` của Spring Security ở order -100 trong cấu hình tương ứng.

Đừng sao chép một con số order từ dự án khác mà không kiểm tra phiên bản và cấu hình đang dùng. Khi custom filter cần chạy trước hoặc sau Spring Security, hãy xác định mục tiêu:

- Request ID/tracing có thể cần tồn tại trước bước xác thực để log được cả request bị từ chối.
- Logic cần principal đã xác thực phải chạy sau Security chain.
- CORS preflight cần được xử lý theo cấu hình CORS tương thích với Security.
- Filter kiểm tra quyền nên nằm trong Spring Security authorization model khi có thể.

Không tạo bộ xác thực thủ công song song với Spring Security chỉ để đặt một WebFilter khác.

## 8. ServerWebExchange: request, response và attributes

`ServerWebExchange` là context của một lần HTTP request-response.

| API | Công dụng |
| --- | --- |
| `exchange.getRequest()` | Đọc request method, URI, headers, cookies và body |
| `exchange.getResponse()` | Thiết lập status, headers và ghi response |
| `exchange.getAttributes()` | Lưu dữ liệu gắn với exchange hiện tại |
| `exchange.getSession()` | Lấy WebSession theo kiểu reactive |
| `exchange.getPrincipal()` | Lấy principal hiện tại theo kiểu reactive |
| `exchange.getLocaleContext()` | Lấy locale context |

Attributes là map gắn với một exchange. Đây là nơi thích hợp để chia sẻ request ID hoặc dữ liệu đã tính giữa các filter và handler trong cùng request.

~~~java
exchange.getAttributes().put("requestId", requestId);
return chain.filter(exchange);
~~~

Handler hoặc filter sau có thể đọc:

~~~java
String requestId = exchange.getAttribute("requestId");
~~~

Không dùng exchange attributes làm cache dùng chung giữa các request. Mỗi exchange có vòng đời riêng; dữ liệu dùng chung cần một bean có quản lý đồng thời và lifecycle thích hợp.

### 8.1. Exchange attributes và Reactor Context

| Cơ chế | Phạm vi | Thích hợp |
| --- | --- | --- |
| Exchange attributes | Một ServerWebExchange | Request ID, dữ liệu cần đọc trực tiếp từ exchange |
| Reactor Context | Một reactive subscription chain | Metadata cần truyền qua các operator/subscriber |
| Singleton/service state | Nhiều request | Cache hoặc cấu hình dùng chung, phải xử lý concurrency |

Reactor Context không phải ThreadLocal. Reactive pipeline có thể chuyển thread; dùng Context hoặc cơ chế context propagation phù hợp thay vì giả định mọi operator chạy trên cùng một thread.

## 9. Thay đổi request trước khi chuyển chain

Request của WebFlux được thiết kế bất biến. Muốn thay đổi header/path hoặc tạo request wrapper, dùng builder của request và exchange.

~~~java
ServerHttpRequest mutatedRequest = exchange.getRequest()
    .mutate()
    .headers(headers ->
        headers.set("X-Internal-Request", "true"))
    .build();

ServerWebExchange mutatedExchange = exchange.mutate()
    .request(mutatedRequest)
    .build();

return chain.filter(mutatedExchange);
~~~

Request tiếp theo trong chain nhìn thấy header nội bộ. Request gốc không bị thay đổi tại chỗ; filter tạo exchange mới bao quanh request đã mutate.

Dùng cách này cho metadata nội bộ có kiểm soát. Không tin header do client tự gửi như `X-User-Role`, `X-Authenticated` hoặc `X-Internal-Request`; xóa hoặc ghi đè header nhạy cảm ở trust boundary và chỉ tạo giá trị sau khi xác thực nguồn.

Nếu chỉ cần truyền dữ liệu nội bộ giữa filter/handler, exchange attributes thường đơn giản hơn việc thêm header vào request.

## 10. Thêm response header và thời điểm commit

Response headers phải được đặt trước khi response commit. Có thể thiết lập trực tiếp trước khi gọi chain:

~~~java
exchange.getResponse().getHeaders()
    .set("X-Application", "reactive-demo");

return chain.filter(exchange);
~~~

Nếu muốn đăng ký callback chạy ngay trước commit, dùng `beforeCommit`:

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
        .set("X-Request-Id", requestId);
    return Mono.empty();
});

return chain.filter(exchange);
~~~

`beforeCommit` phù hợp khi header cần được đặt ngay trước khi server commit response. Callback phải trả publisher; không gọi `block()` bên trong.

Sau khi response đã commit, không thể thay status hoặc headers đã gửi. Filter có thể quan sát kết quả sau chain, nhưng không nên giả định mọi header đều có thể sửa ở callback hậu xử lý.

### 10.1. Response body và ServerHttpResponseDecorator

Nếu cần can thiệp body response, có thể dùng `ServerHttpResponseDecorator` để bọc response và override method ghi body như `writeWith` hoặc `writeAndFlushWith`. Đây là kỹ thuật nâng cao vì body thường là DataBuffer và có yêu cầu:

- Giữ backpressure và không gom stream lớn vào RAM.
- Giải phóng DataBuffer đúng cách nếu đọc/ghi buffer thủ công.
- Xử lý cả `writeWith` và `writeAndFlushWith` khi endpoint streaming.
- Cập nhật Content-Length, ETag hoặc checksum nếu nội dung thay đổi.
- Tránh consume body trước handler rồi khiến handler không còn dữ liệu để đọc.

Nếu chỉ cần thêm header, status hoặc log, không cần bọc body. Chỉ dùng decorator khi yêu cầu thực sự là biến đổi byte/body.

## 11. Session và principal trong WebFilter

WebFlux cung cấp session và principal theo reactive API. Không gọi block để lấy chúng.

Lấy session:

~~~java
return exchange.getSession()
    .flatMap(session -> {
        session.getAttributes().put("lastPath",
            exchange.getRequest().getPath().value());
        return chain.filter(exchange);
    });
~~~

Đây là ví dụ lưu thông tin vào session. Việc đọc/ghi session là bất đồng bộ; session manager của WebFlux quản lý lưu trữ theo lifecycle.

Lấy principal:

~~~java
return exchange.getPrincipal()
    .map(principal -> principal.getName())
    .defaultIfEmpty("anonymous")
    .flatMap(name -> {
        exchange.getAttributes().put("principalName", name);
        return chain.filter(exchange);
    });
~~~

Đoạn này luôn tiếp tục chain sau khi principal được resolve; nếu không có principal, giá trị anonymous được dùng. Trong ứng dụng bảo mật, principal thường do Spring Security cung cấp. Không tự đọc cookie rồi tự kết luận người dùng đã xác thực.

## 12. WebFilter và Spring Security

Spring Security reactive xây dựng bảo mật trên nền WebFilter. Chuỗi `SecurityWebFilterChain` chứa các bước authentication, authorization, exception translation, security context và các filter bảo mật khác.

Nên dùng Spring Security cho:

- Xác thực JWT, OAuth2 Resource Server hoặc form login.
- Phân quyền theo authority/role.
- Quản lý SecurityContext.
- CSRF và CORS theo cấu hình phù hợp.
- Xử lý authentication entry point và access denied.

Custom WebFilter có thể bổ sung correlation ID, audit metadata hoặc quan sát request. Nếu cần principal, hãy đọc từ security context đã được Spring Security thiết lập và đặt order phù hợp.

Không nên viết filter xác thực riêng bằng cách so sánh token hard-coded. Cách đó dễ bỏ sót chữ ký, expiry, issuer, audience, rotation và chính sách phân quyền.

## 13. CORS, forwarded headers và filter hạ tầng

Một số chức năng thường được xử lý ở lớp WebFilter hoặc web infrastructure:

- **CORS:** WebFlux có hỗ trợ CORS và `CorsWebFilter`. Khi dùng Spring Security, cần cấu hình CORS để xử lý đúng thứ tự trước các bước bảo mật liên quan.
- **Observation/metrics:** filter hoặc instrumentation ghi nhận request duration, status và trace context.
- **Session:** `WebSessionManager` cung cấp session reactive.
- **Forwarded headers:** khi chạy sau reverse proxy, host/scheme/port công khai có thể khác kết nối nội bộ. Spring cung cấp `ForwardedHeaderTransformer` để xử lý forwarded headers ở giai đoạn phù hợp.

Forwarded headers có rủi ro trust boundary. Nếu ứng dụng tin mọi `X-Forwarded-*` hoặc `Forwarded` do client gửi, kẻ tấn công có thể giả mạo host/scheme và ảnh hưởng link, redirect hoặc kiểm tra bảo mật. Proxy ở biên phải loại bỏ header giả mạo và chỉ chuyển tiếp giá trị do proxy tin cậy tạo ra.

Không đăng ký nhiều cơ chế xử lý cùng một chức năng nếu chúng xung đột. Kiểm tra auto-configuration của Spring Boot trước khi thêm filter tùy chỉnh.

## 14. WebFilter, HandlerFilterFunction và Servlet Filter

| Cơ chế | Nền tảng | Phạm vi |
| --- | --- | --- |
| `WebFilter` | Spring WebFlux WebHandler API | Toàn bộ reactive HTTP exchange |
| `HandlerFilterFunction` | WebFlux.fn | RouterFunction/functional routes được gắn filter |
| `jakarta.servlet.Filter` | Servlet API | Servlet container filter chain |

Dùng `WebFilter` khi muốn áp dụng chính sách chung trên toàn WebFlux application, gồm controller annotation và functional endpoints.

Dùng `HandlerFilterFunction` khi chỉ muốn filter một nhóm functional routes. Nó nhận ServerRequest và handler tiếp theo, rồi trả ServerResponse publisher.

Dùng Servlet Filter cho ứng dụng Servlet/Spring MVC. Không thay Servlet Filter bằng WebFilter hoặc ngược lại mà không xem xét web application type và runtime.

Ngoài ra:

- `@ControllerAdvice` và `@ExceptionHandler` xử lý lỗi ở tầng controller.
- `WebExceptionHandler` xử lý exception ở WebHandler chain.
- Spring Security reactive quản lý authentication/authorization bằng filter chain chuyên dụng.

Chọn đúng tầng giúp logic nằm đúng phạm vi và dễ kiểm thử.

## 15. Lỗi thường gặp khi triển khai WebFilter

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Không return `chain.filter(exchange)` | Request bị dừng và không đến handler | Return publisher của chain hoặc response chặn có chủ đích |
| Gọi `chain.filter(exchange)` hai lần | Handler/side effect có thể chạy trùng | Tạo downstream publisher một lần và compose |
| Gọi `subscribe()` trong filter | Request lifecycle tách khỏi publisher trả về; lỗi khó truyền đúng | Return Mono<Void> và compose operator |
| Gọi `block()` để lấy session/principal | Chặn event-loop | Dùng flatMap, then, switchIfEmpty |
| Dùng doOnSuccess rồi giả định Mono<Void> có object | Callback nhận null | Chỉ ghi nhận completion, không dereference |
| Dùng doFinally như callback success-only | Cleanup/log có thể chạy cả error và cancel | Phân biệt SignalType hoặc dùng doOnSuccess |
| Dùng onErrorResume bắt mọi lỗi | Che giấu lỗi server và lỗi lập trình | Chỉ map exception cụ thể |
| Ghi response header sau commit | Header đã gửi không thể thay đổi | Đặt trước chain hoặc dùng beforeCommit |
| Đọc request body trong filter mà không wrap/replay | Handler sau có thể không còn body để đọc | Tránh đọc body; nếu bắt buộc, dùng decorator/cache đúng cách |
| Ghi response body trong filter mà không xử lý DataBuffer | Rò rỉ buffer hoặc phá backpressure | Dùng decorator đúng contract và release buffer |
| Tin header xác thực do client gửi | Client có thể giả mạo danh tính/quyền | Dùng Spring Security và ghi đè metadata ở trust boundary |
| Dùng exchange attributes làm global cache | Dữ liệu bị nhầm phạm vi giữa request | Dùng store có quản lý concurrency cho dữ liệu dùng chung |
| Không khai báo order khi có dependency | Thứ tự filter không rõ ràng | Dùng @Order/Ordered và kiểm tra security order |
| Filter log toàn bộ body/header | Có thể lộ token, cookie, PII và tăng tải | Log metadata tối thiểu, mask dữ liệu |
| Xử lý cancel như server error | Metrics/log sai và có thể cố ghi response khi client đã ngắt | Ghi nhận SignalType.CANCEL riêng |
| Đưa logic domain vào global filter | Khó hiểu, khó test và áp dụng quá rộng | Đưa nghiệp vụ vào handler/service |
| Dùng WebFilter thay Spring Security | Thiếu cơ chế authentication/authorization đầy đủ | Dùng SecurityWebFilterChain |
| Bỏ qua request không khớp route | Filter vẫn chạy nhưng có thể hiểu nhầm handler đã xử lý | Tách quan sát filter chain khỏi logic endpoint |

## 16. Java 17+ Spring Boot WebFlux demo hoàn chỉnh

Ví dụ xây dựng một WebFilter tạo trace ID cho mỗi request, đưa ID vào exchange attributes, thêm ID vào response header trước commit và ghi nhận success/error/cancel của filter chain.

### 16.1. Cấu trúc dự án

~~~text
webfilter-demo/
  build.gradle
  src/
    main/java/demo/
      DemoApplication.java
      TraceWebFilter.java
      HelloController.java
    test/java/demo/
      TraceWebFilterTest.java
~~~

### 16.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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

Spring Boot quản lý phiên bản Spring Framework, Reactor và các dependency tương thích. Không tự thêm phiên bản Reactor riêng nếu chưa có yêu cầu tương thích cụ thể.

### 16.3. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 16.4. TraceWebFilter.java

~~~java
package demo;

import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class TraceWebFilter implements WebFilter {
    public static final String TRACE_ID_ATTRIBUTE =
        TraceWebFilter.class.getName() + ".traceId";

    private static final Logger log =
        LoggerFactory.getLogger(TraceWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        final String traceId = UUID.randomUUID().toString();

        // Trước chain: chia sẻ trace ID với handler trong exchange này.
        exchange.getAttributes().put(TRACE_ID_ATTRIBUTE, traceId);

        // Đăng ký header trước khi response commit.
        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders()
                .set("X-Trace-Id", traceId);
            return Mono.empty();
        });

        return Mono.defer(() -> {
            long startedAt = System.nanoTime();

            log.info("Before chain: {} {}",
                exchange.getRequest().getMethod(),
                exchange.getRequest().getURI().getPath());

            return chain.filter(exchange)
                .doOnSuccess(ignored ->
                    log.info("Chain completed: {}", traceId))
                .doOnError(error ->
                    log.warn("Chain failed: {}", traceId, error))
                .doFinally(signal -> {
                    long elapsedMs =
                        (System.nanoTime() - startedAt) / 1_000_000;
                    log.info("After chain: traceId={}, signal={}, elapsed={}ms",
                        traceId, signal, elapsedMs);
                });
        });
    }
}
~~~

Filter tạo UUID ở mỗi exchange. Attribute giúp controller đọc cùng ID; `beforeCommit` thêm ID vào response header trước khi gửi. `doFinally` ghi nhận complete, error và cancel. Ví dụ không đọc body và không giữ state dùng chung giữa các request.

### 16.5. HelloController.java

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public Mono<String> hello(ServerWebExchange exchange) {
        String traceId = exchange.getAttribute(
            TraceWebFilter.TRACE_ID_ATTRIBUTE);

        return Mono.just("hello " + traceId);
    }
}
~~~

Controller đọc trace ID filter đã đặt vào exchange attributes. Body và response header chứa cùng một ID.

### 16.6. TraceWebFilterTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class TraceWebFilterTest {
    @Autowired
    WebTestClient client;

    @Test
    void filterAddsTraceIdToExchangeAndResponse() {
        EntityExchangeResult<String> result = client.get()
            .uri("/hello")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Trace-Id")
            .expectBody(String.class)
            .returnResult();

        String traceId =
            result.getResponseHeaders().getFirst("X-Trace-Id");

        assertNotNull(traceId);
        assertEquals("hello " + traceId, result.getResponseBody());
    }

    @Test
    void filterAlsoWrapsNotFoundResponse() {
        client.get()
            .uri("/route-does-not-exist")
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader().exists("X-Trace-Id");
    }
}
~~~

Test đầu xác minh filter chạy trước handler, truyền trace ID qua exchange attributes và thêm cùng giá trị vào response header. Test thứ hai xác minh filter vẫn bao quanh request không tìm được route.

### 16.7. Chạy ứng dụng và kiểm tra

Chạy tại thư mục dự án:

~~~bash
./gradlew bootRun
~~~

Hoặc:

~~~bash
gradle bootRun
~~~

Gọi endpoint:

~~~bash
curl -i http://localhost:8080/hello
curl -i http://localhost:8080/route-does-not-exist
~~~

Response đầu tiên có dạng:

~~~http
HTTP/1.1 200 OK
X-Trace-Id: 5e4e5a6f-6e90-4b25-8d2f-1f4d4f9e5a21
Content-Type: text/plain;charset=UTF-8

hello 5e4e5a6f-6e90-4b25-8d2f-1f4d4f9e5a21
~~~

Trace ID ở trên chỉ là giá trị minh họa; mỗi request thực tế tạo UUID mới. Request tới route không tồn tại vẫn đi qua WebFilter và nhận header trace ID nếu response chưa commit trước đó.

Chạy test:

~~~bash
./gradlew test
~~~

Hai test tập trung vào contract của filter: dữ liệu được thêm trước khi handler chạy và response header được đặt trước commit. Demo không cần Thread.sleep, không gọi block và không tự subscribe.

## 17. Kiểm thử WebFilter độc lập

Nếu không cần khởi động Spring Boot server, có thể kiểm thử WebFilter bằng WebTestClient bind vào một WebHandler hoặc mock exchange. Một cách khác là dùng Spring MockServerWebExchange để tạo request, rồi gọi trực tiếp filter với chain giả.

Ví dụ ý tưởng test chain:

~~~java
MockServerWebExchange exchange =
    MockServerWebExchange.from(
        MockServerHttpRequest.get("/hello").build());

WebFilterChain chain = currentExchange ->
    currentExchange.getResponse().setComplete();

StepVerifier.create(filter.filter(exchange, chain))
    .verifyComplete();
~~~

Đây là snippet cần import từ `org.springframework.mock.web.server`, `org.springframework.mock.http.server.reactive` và `reactor.test.StepVerifier`. Nó giúp kiểm tra filter không cần controller. Nếu filter dùng `beforeCommit`, test phải kích hoạt response commit hoặc ghi response để xác minh callback đã chạy; chỉ gọi `filter()` và verify complete chưa nhất thiết chạy commit callback.

Các tình huống đáng kiểm thử:

- Filter gọi chain đúng một lần.
- Filter chặn request thì chain phía sau không được gọi.
- Request ID/attributes được truyền tới handler.
- Header được thêm trước commit.
- Error được quan sát và tiếp tục truyền hoặc được map đúng.
- Cancellation kích hoạt cleanup phù hợp.
- Thứ tự filter theo cấu hình được xác minh khi có dependency order.

## 18. Checklist thiết kế WebFilter

Trước khi triển khai, trả lời các câu hỏi:

1. Filter cần chạy cho toàn bộ WebFlux request hay chỉ một nhóm route?
2. Logic cần thực hiện trước chain, sau success, sau error hay cả cancel?
3. Filter có gọi chain đúng một lần và return đúng publisher không?
4. Có cần exchange attributes, Reactor Context hay một service dùng chung?
5. Request/response có cần mutate không; thời điểm commit là khi nào?
6. Filter có vô tình đọc/consume body trước handler không?
7. Có blocking I/O, block hoặc subscribe thủ công không?
8. Có cần @Order/Ordered; thứ tự với Spring Security/CORS/observation là gì?
9. Error được propagate hay map; response đã commit chưa?
10. Cancellation có được phân biệt với error không?
11. Log/metrics có lộ token, cookie, body hoặc dữ liệu cá nhân không?
12. Đã kiểm thử request thành công, lỗi, route không khớp và cancel chưa?

| Nhu cầu | Giải pháp |
| --- | --- |
| Ghi log trước khi request đi tiếp | Logic trước `chain.filter` hoặc `Mono.defer` |
| Ghi log sau success | `doOnSuccess` hoặc `then` |
| Ghi log khi lỗi | `doOnError` |
| Cleanup mọi terminal signal | `doFinally` |
| Chặn request | Đặt status và return `response.setComplete()` |
| Truyền request ID cho handler | `exchange.getAttributes()` |
| Thêm response header | `getResponse().getHeaders()` trước commit hoặc `beforeCommit` |
| Thay request header | `request.mutate()` rồi `exchange.mutate()` |
| Đọc session | `exchange.getSession()` |
| Đọc principal | `exchange.getPrincipal()` |
| Authentication/authorization | Spring Security reactive |
| Filter riêng cho WebFlux.fn | `HandlerFilterFunction` |
| Kiểm thử | WebTestClient, MockServerWebExchange, StepVerifier |

## 19. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** WebFilter có method nào và trả về kiểu gì?

**Đáp án:** `filter(ServerWebExchange, WebFilterChain)` và trả `Mono<Void>` biểu diễn quá trình request/response hoàn tất.

**Câu 2.** `chain.filter(exchange)` có tác dụng gì?

**Đáp án:** Chuyển request sang filter tiếp theo hoặc WebHandler cuối cùng. Nếu không gọi chain, filter có thể chặn request bằng một response riêng.

**Câu 3.** Muốn log sau khi chain kết thúc dù complete, error hay cancel, dùng operator nào?

**Đáp án:** `doFinally` vì nó nhận `SignalType` cho các terminal signal.

**Câu 4.** `doOnSuccess` trên `Mono<Void>` có thể nhận giá trị null không?

**Đáp án:** Có. Mono<Void> hoàn tất thành công mà không phát object; callback không được dereference tham số.

**Câu 5.** Có nên gọi `subscribe()` bên trong WebFilter không?

**Đáp án:** Không. Hãy return và compose publisher để WebFlux quản lý lifecycle và truyền lỗi/cancel đúng cách.

**Câu 6.** Filter A có order 1, filter B có order 2. Request đi vào theo thứ tự nào?

**Đáp án:** A trước rồi B. Khi chain unwind, callback hậu xử lý của B thường chạy trước callback của A.

**Câu 7.** Muốn thêm response header ngay trước commit thì dùng API nào?

**Đáp án:** `exchange.getResponse().beforeCommit(...)`. Callback phải trả Mono<Void> và không block.

**Câu 8.** Exchange attributes có thể dùng làm cache giữa mọi request không?

**Đáp án:** Không. Attributes thuộc một ServerWebExchange. Cache dùng chung cần một component riêng có quản lý concurrency và lifecycle.

**Câu 9.** Nếu client hủy request, filter nên xem đó là server error không?

**Đáp án:** Không mặc định. Cancel là tín hiệu hủy subscription; ghi nhận riêng bằng doOnCancel hoặc doFinally.

**Câu 10.** Nên dùng WebFilter hay HandlerFilterFunction cho một nhóm route WebFlux.fn?

**Đáp án:** HandlerFilterFunction phù hợp nếu chỉ muốn áp dụng cho router/functional routes được gắn filter. WebFilter áp dụng ở tầng WebHandler và có phạm vi rộng hơn.

**Câu 11.** Có nên dùng WebFilter tự kiểm tra JWT bằng một chuỗi hard-coded không?

**Đáp án:** Không. Dùng Spring Security reactive để xác thực, xác minh chữ ký, issuer, audience, expiry và phân quyền.

**Câu 12.** Vì sao filter không nên đọc toàn bộ request body chỉ để ghi log?

**Đáp án:** Body là stream có thể chỉ được tiêu thụ một lần; việc đọc trước có thể khiến handler sau không còn dữ liệu, tăng RAM và làm hỏng backpressure. Chỉ wrap/cache body khi có yêu cầu rõ ràng và hiểu cách quản lý DataBuffer.

## 20. Ghi nhớ và tài liệu chính thức

- `WebFilter` là interception layer trong WebFlux WebHandler chain, có thể áp dụng logic trước và sau phần xử lý còn lại.
- `WebFilterChain.filter(exchange)` chuyển request đi tiếp và trả `Mono<Void>`.
- Dùng `doOnSuccess`, `doOnError` và `doFinally` để phân biệt success, error và cancel.
- Filter order nhỏ hơn chạy sớm hơn ở request path; callback hậu xử lý thường unwind theo chiều ngược.
- Spring Boot tự đăng ký WebFilter bean; dùng `@Order` hoặc `Ordered` khi thứ tự có ý nghĩa.
- `ServerWebExchange` cung cấp request, response, attributes, session và principal.
- Thêm header trước response commit; sau commit không thể đổi header/status đã gửi.
- Không block, không subscribe thủ công, không gọi chain nhiều lần.
- Dùng Spring Security reactive cho authentication/authorization; dùng HandlerFilterFunction cho phạm vi functional route.
- Đọc body hoặc bọc DataBuffer trong filter đòi hỏi quản lý backpressure và lifecycle cẩn thận.

Tài liệu chính thức:

1. [Spring Framework Reference — Reactive Core, Filters](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): WebFilter trong WebHandler chain, đăng ký bean, thứ tự filter, CORS và exception handling.
2. [Spring Boot Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): tự động phát hiện WebFilter bean và thứ tự filter do Boot cấu hình.
3. [Spring Framework Javadoc — WebFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html): contract filter(ServerWebExchange, WebFilterChain).
4. [Spring Framework Javadoc — WebFilterChain](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilterChain.html): delegate tới filter tiếp theo.
5. [Spring Framework Javadoc — ServerWebExchange](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html): request, response, attributes, session và principal.
6. [Spring Framework Javadoc — ServerHttpResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html): response headers, commit và body writing.
7. [Spring Security Reference — Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/index.html): SecurityWebFilterChain, authentication và authorization trên WebFlux.
8. [Project Reactor Reference — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): doOnError, onErrorResume và terminal signals.

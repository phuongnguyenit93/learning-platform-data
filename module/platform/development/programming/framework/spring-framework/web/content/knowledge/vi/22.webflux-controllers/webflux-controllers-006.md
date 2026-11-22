# Spring WebFlux — @ExceptionHandler, @RestControllerAdvice và ProblemDetail

## 1. Mục tiêu

Spring WebFlux cần một hợp đồng lỗi HTTP nhất quán ngay cả khi exception đến từ một `Mono`, `Flux`, binding request, validation, business service hoặc framework handler. Một API tốt phải truyền đạt lỗi cho client theo **HTTP status + error code + body an toàn**, thay vì gửi stacktrace hoặc trả 200 cho mọi thất bại.

Bài này tập trung vào annotated WebFlux controllers:

- Xử lý riêng một controller bằng `@ExceptionHandler`.
- Tái sử dụng chính sách xử lý lỗi giữa controllers bằng `@RestControllerAdvice`.
- Dùng `ProblemDetail` theo **RFC 9457 — Problem Details for HTTP APIs** và media type `application/problem+json`.
- Hiểu `ErrorResponse`, `ErrorResponseException`, `ResponseStatusException` và `ResponseEntityExceptionHandler`.
- Phân biệt `WebExchangeBindException` với `HandlerMethodValidationException`; bảo toàn HTTP 400, 404, 405, 409, 415, 500 và 504.
- Hiểu thứ tự giữa local exception methods, nhiều advice, `@Order`, root/cause matches.
- Biết giới hạn của controller advice đối với `WebFilter`, WebExceptionHandler, Spring Security, reverse proxy và response đã committed.
- Tạo ví dụ chạy độc lập **Java 17 / Spring Boot 3.5.0 / Spring Framework 6.2 / Maven**, kiểm bằng `WebTestClient`.
- Thiết kế error contract, i18n, requestId/traceId, logging và bảo vệ thông tin nhạy cảm.

Đề bài thuộc nhóm **Controller WebFlux**. Spring MVC cũng có những annotations cùng tên nhưng dùng Servlet `DispatcherServlet`; WebFlux dùng reactive `DispatcherHandler` và các types tương ứng. Không copy WebMVC-specific exception-handler signatures sang WebFlux mà không đối chiếu Javadoc.

## 2. Request đi qua những lớp xử lý nào?

Mô hình khái quát:

~~~text
Browser / API client
        |
        v
Reactor Netty / HTTP server
        |
        v
WebHttpHandlerAdapter + WebFilter chain
        |
        v
DispatcherHandler
        |
        +--> HandlerMapping (chọn route)
        |
        +--> HandlerAdapter (gọi controller)
        |
        +--> Mono / Flux / return value
        |
        +--> @ExceptionHandler tại controller
        |             hoặc @RestControllerAdvice
        |
        +--> HandlerResultHandler / codecs
        |
        v
HTTP status, headers, response body
~~~

Ngoài annotated controller resolution còn có các `WebExceptionHandler` trong WebHandler chain, lỗi được Spring Boot mặc định xử lý, phản hồi do Spring Security reactive tạo, và gateway/proxy failures. Chúng **không đồng nhất** với controller advice.

| Phạm vi | Cơ chế | Thích hợp |
| --- | --- | --- |
| Một annotated controller | `@ExceptionHandler` | Lỗi có hợp đồng đặc biệt của controller |
| Nhiều annotated controllers | `@RestControllerAdvice` | Lỗi domain, validation, API error schema |
| Built-in WebFlux exceptions | `ResponseEntityExceptionHandler` | Chuẩn hóa ErrorResponse của Spring |
| Web handler/filter chain | `WebExceptionHandler` | Lỗi nằm ngoài annotated controller processing |
| Boot reactive fallback | `ErrorWebExceptionHandler` | Lỗi chưa được các tầng trên xử lý |
| Reactive Spring Security | `SecurityWebFilterChain`, entry point/access denied handler | 401/403 liên quan authentication/authorization |
| Edge/gateway | Envoy/Nginx/CDN | Có thể tự trả 502/504/429 |

**Không giả định** một `@RestControllerAdvice` sẽ bắt tất cả exceptions từ `WebFilter`. WebFilter thường chạy ngoài `DispatcherHandler`, do vậy lỗi có thể được xử lý bởi WebExceptionHandler/Boot error layer. Và nếu proxy tự trả 504 thì request thậm chí chưa từng tới controller.

### 2.1. Exception và Reactor error signal

~~~java
@GetMapping("/api/items/{id}")
Mono<Item> get(@PathVariable long id) {
    return service.find(id);
}
~~~

Nếu `service.find(id)` trả một `Mono.error(new ItemNotFoundException(...))` trước khi response committed, Spring WebFlux có thể định tuyến lỗi tới controller-local hoặc global exception handler thích hợp.

Một ngoại lệ **được throw đồng bộ** trong quá trình handler invocation hoặc một **onError signal** từ publisher thuộc lifecycle request đều có thể tham gia cơ chế xử lý WebFlux, nhưng chi tiết và thời điểm phụ thuộc response state.

Tránh gọi `subscribe()` ngay trong controller chỉ để chạy một task rồi return `Mono.just("ok")`: tác vụ fire-and-forget sẽ ra ngoài request lifecycle, lỗi/cancellation không còn do HTTP handler quản lý tự nhiên.

## 3. @ExceptionHandler trong controller

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    Mono<OrderDto> get(@PathVariable long id) {
        return orders.find(id);
    }

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> missing(
            OrderNotFoundException exception) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Không tìm thấy đơn hàng");
        p.setProperty("code", "ORDER_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(p);
    }
}
~~~

Đây là **fragment**: `OrderService`, `OrderDto`, exception và imports chưa được định nghĩa; dự án độc lập nằm ở mục 13.

### 3.1. Annotation matching

Có thể khai báo exception type trong annotation:

~~~java
@ExceptionHandler(OrderNotFoundException.class)
ProblemDetail handle(OrderNotFoundException error) { ... }
~~~

Hoặc để framework suy từ method parameter:

~~~java
@ExceptionHandler
ProblemDetail handle(OrderNotFoundException error) { ... }
~~~

Nên ưu tiên một exception type rõ ràng và chữ ký cụ thể, tránh bắt mọi `RuntimeException` nếu bạn thật sự chỉ cần xử lý một lỗi domain.

Spring có thể match root exception hoặc một cause trong wrapper exception. Một wrapped exception không có nghĩa handler luôn nhận lớp wrapper; hãy test nested causes và chọn rõ ràng loại exception phù hợp.

### 3.2. Tham số và return types

WebFlux exception handler có thể nhận `Throwable` tương ứng, `ServerWebExchange`, request/response interfaces và một số context arguments. Có thể trả:

- `ProblemDetail`.
- `ResponseEntity<ProblemDetail>`.
- `Mono<ProblemDetail>` hoặc `Mono<ResponseEntity<ProblemDetail>>`.
- `ErrorResponse` hoặc DTO lỗi khác mà codecs hỗ trợ.

Ví dụ asynchronous return:

~~~java
@ExceptionHandler(InventoryUnavailableException.class)
Mono<ResponseEntity<ProblemDetail>> unavailable(
        InventoryUnavailableException exception) {
    ProblemDetail p = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Dịch vụ kiểm tra tồn kho đang bận");
    p.setProperty("code", "INVENTORY_UNAVAILABLE");
    return Mono.just(ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE).body(p));
}
~~~

Đây là fragment. Nếu không thực sự cần compose non-blocking operations, trả trực tiếp `ProblemDetail`/`ResponseEntity` đơn giản hơn. Không thực hiện blocking network/database calls trong exception handler chỉ để làm đẹp nội dung lỗi.

Các `@ExceptionHandler` methods không hỗ trợ tất cả arguments của `@RequestMapping`, đặc biệt request-body và `@ModelAttribute`-related method arguments; không coi đây là một handler input-binding method thứ hai.

## 4. @RestControllerAdvice và phạm vi áp dụng

`@RestControllerAdvice` kết hợp `@ControllerAdvice` với `@ResponseBody` để các handler methods có body được serialize qua HttpMessageWriter. Nó phù hợp cho một API thống nhất toàn hệ thống.

~~~java
@RestControllerAdvice
class ApiErrors {

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail missing(OrderNotFoundException ex) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy tài nguyên");
        p.setProperty("code", "ORDER_NOT_FOUND");
        return p;
    }
}
~~~

**Khác biệt:** `@ControllerAdvice` cũng có thể dùng với `@ExceptionHandler`, nhưng `@RestControllerAdvice` thể hiện rõ ý định trả response body, không view template.

### 4.1. Local handler trước global handler

Nếu một controller có method `@ExceptionHandler(OrderNotFoundException.class)` và một global advice cũng bắt loại đó, local controller method thường được xét trước global advice cho lỗi phát sinh tại controller tương ứng.

Điều này có ích cho exception cần xử lý rất đặc thù. Nhưng lạm dụng local handlers có thể làm cùng error code trả schema/status khác nhau ở nhiều endpoints. Nên chuẩn hóa domain error catalog và chỉ override khi thật sự có một hợp đồng khác.

### 4.2. Giới hạn advice bằng selectors

Có thể chỉ áp dụng advice cho một package:

~~~java
@RestControllerAdvice(basePackages = "com.example.api")
class PublicApiErrors {
}
~~~

Hoặc theo controller annotation:

~~~java
@RestControllerAdvice(annotations = RestController.class)
class RestOnlyErrors {
}
~~~

Có thể dùng `basePackageClasses` thay chuỗi package để refactor an toàn hơn. Các selector có runtime matching cost, vì thế không thêm nhiều selector phức tạp nếu một global advice đủ.

### 4.3. Nhiều advice và @Order

Ví dụ:

~~~java
@Order(-1)
@RestControllerAdvice
class DomainErrors {
}

@Order(100)
@RestControllerAdvice
class OptionalFallbackErrors {
}
~~~

Đây là fragments. Advice được xét theo `Ordered`/`@Order`. Với một advice, root match ưu tiên cause match, nhưng **cause match trong advice có thứ tự ưu tiên cao hơn** có thể thắng root match của advice thấp hơn.

Rủi ro thường gặp: một advice ưu tiên cao có:

~~~java
@ExceptionHandler(Exception.class)
ProblemDetail everything(Exception ex) {
    return ProblemDetail.forStatus(
            HttpStatus.INTERNAL_SERVER_ERROR);
}
~~~

Nó có thể vô tình đổi những framework errors đúng 400/405/415 thành 500. Với Spring Boot, đây còn có thể can thiệp vào ProblemDetails handler được auto-configure. Chỉ viết catch-all khi bạn thực sự quản lý **toàn bộ** HTTP error semantics và có regression tests đầy đủ.

## 5. RFC 9457 — Problem Details

RFC 9457 cung cấp định dạng error response có thể đọc bởi người và máy.

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Không tìm thấy tài nguyên",
  "instance": "/api/widgets/42"
}
~~~

### 5.1. Năm trường cơ bản

| Field | Ý nghĩa | Best practice |
| --- | --- | --- |
| `type` | URI xác định problem type | URI ổn định, có thể dẫn đến tài liệu; mặc định `about:blank` |
| `title` | Nhãn ngắn gọn của loại lỗi | Cố gắng ổn định theo type, có thể i18n |
| `status` | HTTP status | Đồng nhất status line thực tế |
| `detail` | Thông tin dễ hiểu cho occurrence | Không chứa SQL, secret, stacktrace, PII |
| `instance` | URI reference đến occurrence | Có thể là request path, tránh đưa token/query nhạy cảm |

Các extension properties có thể được bổ sung theo hợp đồng API: `code`, `requestId`, `invalidFields` và các fields khác. RFC không bắt buộc tất cả clients dùng fields mở rộng.

### 5.2. Tạo ProblemDetail trong Spring

~~~java
ProblemDetail p = ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT,
        "Trạng thái đơn hàng không cho phép thao tác");
p.setTitle("Conflict");
p.setProperty("code", "ORDER_CONFLICT");
~~~

Khi return trực tiếp `ProblemDetail`, Spring có thể lấy `status` để đặt HTTP status và ưu tiên `application/problem+json`. Với `ResponseEntity`, phải bảo đảm status line không mâu thuẫn:

~~~java
return ResponseEntity.status(HttpStatus.CONFLICT).body(p);
~~~

Đừng trả HTTP 200 với body có `status=409`. HTTP clients/proxy/metrics sẽ nhìn status line trước.

### 5.3. type URI

Khi cần stable machine-readable distinction:

~~~java
p.setType(URI.create(
        "https://api.example.com/problems/order-conflict"));
p.setTitle("Order conflict");
p.setProperty("code", "ORDER_CONFLICT");
~~~

URL chỉ là ví dụ. Nếu sử dụng type URIs thật, nên cung cấp tài liệu cho clients, giữ URI ổn định qua thời gian và không xây nó từ request `Host` chưa tin cậy.

### 5.4. Extension properties ra JSON top-level

~~~java
p.setProperty("code", "WIDGET_NOT_FOUND");
p.setProperty("requestId", "example-7ab...");
~~~

Spring kết hợp Jackson `ProblemDetailJacksonMixin`, cho phép map properties được unwrapped thành JSON fields top-level:

~~~json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Không tìm thấy tài nguyên",
  "instance": "/api/widgets/42",
  "code": "WIDGET_NOT_FOUND",
  "requestId": "example-7ab..."
}
~~~

`requestId` trong ví dụ không phải giá trị thật. Không tái sử dụng một singleton `ProblemDetail` rồi mutate cho nhiều requests: nó là object có trạng thái có thể chỉnh, dễ gây data race và lẫn metadata giữa clients.

### 5.5. Giữ meaning của status và code khác nhau

- HTTP status 404: loại vấn đề protocol.
- `code=WIDGET_NOT_FOUND`: loại vấn đề của ứng dụng.
- `requestId`: tìm request cụ thể trong logs, không dùng làm error type.
- `traceId`: liên kết nhiều service spans.
- `detail/title`: văn bản hiển thị, có thể được dịch.

Client phải phân nhánh theo status/code/type, không parse chuỗi Vietnamese trong detail để ra quyết định nghiệp vụ.

## 6. ErrorResponse và ErrorResponseException

Spring Framework 6.2 cung cấp:

- `ProblemDetail`: model biểu diễn response body.
- `ErrorResponse`: contract chứa status, headers, body và message codes/arguments.
- `ErrorResponseException`: exception có thể mang error response.
- `ResponseStatusException`: dùng khi request handler muốn biểu diễn HTTP status/optional reason.
- `ResponseEntityExceptionHandler`: base class dành cho global advice xử lý built-in WebFlux exceptions theo RFC 9457.

Ví dụ `ResponseStatusException`:

~~~java
return repository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Item not found")));
~~~

Đây là fragment. Với một ứng dụng nhiều use cases, domain service thường nên ném `WidgetNotFoundException` không gắn HTTP status, còn tầng WebFlux advice quyết định 404 + code.

### 6.1. ErrorResponseException khi muốn exception mang metadata

~~~java
ProblemDetail p = ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT, "Version mismatch");

throw new ErrorResponseException(
        HttpStatus.CONFLICT, p, null);
~~~

Đây là fragment với Spring 6.2 API. Cần nhất quán với error catalog, tránh trộn nhiều loại exception cho cùng business failure mà không có chính sách.

### 6.2. WebFlux ResponseEntityExceptionHandler

Import của WebFlux (khác Servlet MVC):

~~~java
import org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler;
~~~

Một cách triển khai:

~~~java
@RestControllerAdvice
class FrameworkErrorAdvice extends ResponseEntityExceptionHandler {
}
~~~

Spring base class xử lý `ErrorResponse` exceptions và hỗ trợ i18n/message code resolution. Khi override protected methods, dùng đúng **WebFlux 6.2 signatures**, không copy methods từ MVC `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler`.

Không bắt buộc vừa tự kế thừa base class vừa để Boot tạo handler trùng mà không định nghĩa precedence.

### 6.3. Spring Boot Problem Details

Với Spring Boot 3.5 WebFlux:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

Boot có thể auto-configure một `ResponseEntityExceptionHandler` xử lý built-in WebFlux errors theo ProblemDetail. Điều này phù hợp với mô hình:

1. Boot giải quyết những errors của framework như malformed body, unsupported media type, method not allowed.
2. Một custom `@RestControllerAdvice` chỉ xử lý specific domain errors.
3. Khi custom validation body format, đặt advice phù hợp `@Order` và test interaction với Boot handler.

Spring docs ghi nhận advice Boot cho trường hợp này có order 0; custom advice có thể dùng `@Order(-1)` để được chọn trước cho specific exceptions.

**Không có bảo đảm** property này đồng nhất phản hồi của Security filter, reverse proxy, raw WebFilter và streaming transport failures. Chúng thuộc những layers khác.

## 7. Validation trong WebFlux: hai loại exception

Spring WebFlux 6.2 phân biệt validation theo từng argument và method validation.

### 7.1. WebExchangeBindException

Thông thường với `@Valid @RequestBody` trên DTO:

~~~java
record CreateWidgetRequest(
        @NotBlank @Size(max = 80) String name) {
}

@PostMapping("/widgets")
Mono<Widget> create(
        @Valid @RequestBody CreateWidgetRequest request) {
    return service.create(request);
}
~~~

Khi body không đạt Bean Validation, WebFlux có thể ném `WebExchangeBindException`. Để hoạt động, classpath cần Jakarta Bean Validation provider, ví dụ `spring-boot-starter-validation`.

Exception có các field/global errors để app map thành ProblemDetail phù hợp. Không gửi rejected value của password, token hoặc raw body về client.

### 7.2. HandlerMethodValidationException

Khi annotation constraint đặt **trực tiếp** trên method parameter:

~~~java
@GetMapping("/widgets/{id}")
Mono<Widget> get(@PathVariable @Min(1) long id) {
    return service.find(id);
}
~~~

Spring WebFlux built-in method validation có thể ném `HandlerMethodValidationException` nếu `id=0`. Loại này cũng có thể phát sinh khi return-value constraints sai.

**Không gộp mọi HandlerMethodValidationException thành 400.** Với return-value validation violation, status có thể là 500 vì lỗi nằm phía server; dùng `ex.getStatusCode()`/validation source để bảo toàn semantics.

Nếu class controller có `@Validated` mức class, method validation có thể qua AOP path thay vì built-in support. Với Spring 6.2, đừng thêm class-level `@Validated` chỉ để kích hoạt constraints nếu chưa kiểm cơ chế.

### 7.3. Ví dụ validation error body an toàn

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Dữ liệu đầu vào không hợp lệ",
  "code": "VALIDATION_FAILED",
  "invalidFields": ["email", "name"]
}
~~~

Trường `invalidFields` nên dùng safe field names/violation codes, sort/deduplicate và có giới hạn. Không trả:

~~~json
{
  "field": "password",
  "rejectedValue": "plain-text-user-password"
}
~~~

Nếu cần localized field messages, dùng `MessageSource` và mã message được whitelist. Raw validation messages có thể chứa interpolated input; hãy review trước khi public.

### 7.4. Những lỗi input khác vẫn thuộc framework

| Lỗi | HTTP status điển hình |
| --- | --- |
| Body không có hoặc JSON sai | 400 |
| Bean validation input | 400 |
| Method parameter constraint | 400 |
| Method return constraint | 500 |
| Unsupported Content-Type | 415 |
| Không thỏa Accept | 406 |
| HTTP method không được hỗ trợ | 405 |
| Query/header bắt buộc bị thiếu | 400 |

Không để một `@ExceptionHandler(Exception.class)` nuốt các status này và trả 500 chung.

## 8. Error status và domain code

| Điều kiện | Status | Code ví dụ |
| --- | --- | --- |
| Validation/input sai | 400 | `VALIDATION_FAILED` |
| Chưa đăng nhập | 401 | `AUTH_REQUIRED` |
| Không có quyền | 403 | `ACCESS_DENIED` |
| Không có resource | 404 | `WIDGET_NOT_FOUND` |
| Method không hỗ trợ | 405 | Built-in handling |
| Accept không phù hợp | 406 | Built-in handling |
| Business conflict | 409 | `WIDGET_CONFLICT` |
| ETag precondition sai | 412 | `PRECONDITION_FAILED` |
| Content-Type không phù hợp | 415 | Built-in handling |
| Rate limit | 429 | `RATE_LIMITED` |
| Lỗi nội bộ | 500 | `INTERNAL_ERROR` |
| Service phụ trợ tạm ngừng | 503 | `UPSTREAM_UNAVAILABLE` |
| Upstream timeout (gateway role) | 504 | `UPSTREAM_TIMEOUT` |
| Client đóng socket/cancel | Không tự có một HTTP status chuẩn mới | Cleanup/cancel, không gửi thêm body |

Nginx có thể ghi 499 cho client closed request trong access logs; đó là **non-standard proxy log status**, không phải status chuẩn mà WebFlux nên cố gửi tới một client đã ngắt.

Status/code mapping phải gắn với semantics API. Không auto-map mọi timeout thành 504 nếu dịch vụ không hoạt động như gateway/upstream proxy; với use case khác, 503 hoặc contract riêng có thể hợp lý.

## 9. Reactive exception flow

### 9.1. Throw và Mono.error

Trong một reactive service:

~~~java
return repository.findById(id)
        .switchIfEmpty(Mono.error(
                new WidgetNotFoundException()));
~~~

`Mono.error` truyền lỗi vào subscriber; WebFlux có thể xử lý trong controller exception resolution khi request chưa committed.

Không dùng:

~~~java
remoteOperation().subscribe(
        value -> log.info("done"),
        ex -> log.warn("error", ex));
return Mono.just("started");
~~~

trong controller cho công việc thuộc request. Subscription được tạo thủ công có lifecycle riêng; `@ExceptionHandler` không còn bảo đảm xử lý kết quả/error của nó như HTTP response.

### 9.2. Service recovery vs HTTP error rendering

~~~java
return primary.fetch(id)
        .onErrorResume(TransientUpstreamException.class,
                error -> cache.find(id));
~~~

Nếu recovery thành công, advice không cần chạy. `onErrorResume` **không** “quay lại tiếp tục cùng Flux nguồn” ở vị trí lỗi; nó chuyển sang publisher thay thế. Dùng fallback khi API contract cho phép cache/stale data.

### 9.3. Translate technical error

~~~java
return remote.fetch(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorMap(TimeoutException.class,
                UpstreamTimeoutException::new);
~~~

Một advice có thể map `UpstreamTimeoutException` sang `504 UPSTREAM_TIMEOUT`. Đừng để service trực tiếp quyết định `ResponseEntity` nếu muốn tái sử dụng domain code.

### 9.4. Cancellation khác onError

Browser đóng SSE hoặc subscriber gọi `cancel()` không nhất thiết phát `onError`. Quản lý cleanup bằng `using/usingWhen/doFinally` theo publisher lifecycle; không gửi HTTP 500 chỉ vì downstream không còn cần dữ liệu.

## 10. Error boundary ngoài ControllerAdvice

### 10.1. WebFilter

Trong WebFlux, `WebFilter` chạy ở web handler chain, có thể trước annotated controller resolution:

~~~java
@Component
class ExampleFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        return chain.filter(exchange);
    }
}
~~~

Đây là fragment minh họa. Nếu filter phát exception, controller advice không bảo đảm nhận nó. Cần đánh giá `WebExceptionHandler` hoặc Boot ErrorWebExceptionHandler nếu thực sự quản lý filter-level errors. Custom handlers phải tính đến ordering, cancellation và committed status.

### 10.2. Spring Security

Reactive Security tạo 401/403 qua `SecurityWebFilterChain`, `ServerHttpSecurity`, authentication entry points và access denied handlers. Trạng thái auth có thể được xử lý **trước khi controller chạy**, do vậy không dùng domain advice như công cụ duy nhất để chuẩn hóa Security errors.

Không nới lỏng auth chỉ để CORS preflight “hết báo lỗi”; thiết kế Reactive CORS/security đúng các tầng.

### 10.3. WebClient upstream errors

`WebClient.retrieve()` có thể phát `WebClientResponseException` cho 4xx/5xx response từ upstream. HTTP 404 của upstream **không mặc định** có nghĩa client API của bạn phải nhận 404. Hãy map theo domain:

- Upstream authoritative catalog không có item → có thể 404.
- Upstream optional service không có cache → có thể fallback.
- Upstream 503/network timeout → có thể 503/504.
- Upstream 401 do backend credential lỗi → không được tùy tiện leak body/credential details.

Không echo raw upstream body hoặc query URLs chứa tokens vào public ProblemDetail.

### 10.4. Gateway/proxy

Một CDN, gateway hoặc ingress có thể tạo 502/504 bên ngoài Spring. Controller advice không thể áp dụng cho response đó. Khi cần hợp đồng lỗi thống nhất cross-service, phải thỏa thuận schema/status giữa services và gateway, rồi test ở external ingress.

## 11. HTTP response đã committed: giới hạn không thể bỏ qua

Với Server-Sent Events:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: {"percent":20}
~~~

Sau khi status/headers đã gửi, một `Flux` error **không thể đổi cùng response thành**:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json

{"status":500,"detail":"Internal server error"}
~~~

Nếu stream vẫn usable và lỗi là business-level, có thể gửi một **SSE application error event**:

~~~text
event: app-error
data: {"code":"JOB_FAILED","message":"Không thể tiếp tục"}

~~~

Status HTTP vẫn là 200. Frontend phải phân biệt transport success với application event outcome.

Khi transport write lỗi hoặc client đã disconnect, **không cố write ProblemDetail JSON hay error SSE event thứ hai**. Dừng publisher, cleanup resource, ghi log/metrics thích hợp. Một exception handler không thể đảo ngược bytes đã gửi; đây là HTTP protocol constraint.

## 12. Thiết kế an toàn, i18n, correlation

### 12.1. Contract gợi ý

~~~json
{
  "type": "https://api.example.com/problems/widget-not-found",
  "title": "Widget not found",
  "status": 404,
  "detail": "Không tìm thấy tài nguyên yêu cầu",
  "instance": "/api/widgets/123",
  "code": "WIDGET_NOT_FOUND",
  "requestId": "example-2b7..."
}
~~~

HTTP status, `code/type` mới là machine-readable source of truth; `detail/title` có thể dịch hoặc cải tiến nội dung.

### 12.2. Redact sensitive data

Không trả:

- Exception stacktrace / exception class + Java package nội bộ.
- SQL query, database URL, username/password, access token/cookie.
- File system paths, internal DNS names, private IP/port.
- Raw upstream response body có thể chứa customer records.
- Validation rejected values của password, API key hoặc personal data.

Tránh:

~~~java
problem.setDetail(exception.getMessage());
~~~

với generic unexpected errors. Thay bằng public message constant an toàn và log thông tin hữu ích **server-side**. Logs cũng phải bảo vệ secrets và có retention/access policy.

### 12.3. Request ID và trace ID

- Request ID phân biệt request cụ thể.
- Trace ID liên kết nhiều downstream spans trong distributed tracing.
- Error code mô tả loại lỗi ổn định.

Với cross-origin SPA đọc response header `X-Request-ID`, cần CORS exposedHeaders thích hợp. Không tin raw header do client tự gửi làm authority cho log correlation nếu không validate/normalize.

### 12.4. ErrorMessage internationalization

Spring `ErrorResponse` có message codes/arguments cho `type/title/detail`; `ResponseEntityExceptionHandler` hỗ trợ giải quyết thông qua `MessageSource`. Bạn có thể dịch title/detail theo locale, trong khi `code` và HTTP status không đổi.

Một ứng dụng i18n cần xác định locale resolution, fallback language và safe interpolation. Không để error detail locale-dependent trở thành điều kiện rẽ nhánh của frontend SDK.

## 13. Dự án Maven độc lập: WebFlux ProblemDetail API

Demo gồm:

- POST `/api/widgets` tạo Widget, dùng `@Valid @RequestBody`.
- GET `/api/widgets/{id}`, dùng direct constraint `@Min(1)`.
- GET `/api/demo/conflict` trả 409.
- GET `/api/demo/timeout` dùng Reactor timeout và trả 504.
- GET `/api/demo/crash` trả 500 generic, không lộ exception message có secret.
- Built-in 405, 415 và malformed JSON được Boot Problem Details xử lý.
- WebTestClient tests chứng minh HTTP status, code, response schema và redaction.

### 13.1. Cấu trúc

~~~text
webflux-problem-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/WebFluxProblemApplication.java
    │   └── resources/application.properties
    └── test/java/demo/WebFluxProblemTest.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>webflux-problem-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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
~~~

### 13.3. application.properties

~~~properties
server.port=8080
spring.webflux.problemdetails.enabled=true

# Production: configure authentication, monitoring and safe logging.
~~~

### 13.4. WebFluxProblemApplication.java

Lưu tất cả code dưới đây trong **một file** `src/main/java/demo/WebFluxProblemApplication.java`. Chỉ có một top-level public class, các record/class khác package-private; Java 17 hỗ trợ cấu trúc này.

~~~java
package demo;

import java.net.URI;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxProblemApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxProblemApplication.class, args);
    }
}

record CreateWidgetRequest(
        @NotBlank @Size(max = 80) String name) {
}

record Widget(long id, String name) {
}

class WidgetNotFoundException extends RuntimeException {
}

class WidgetConflictException extends RuntimeException {
}

class UpstreamTimeoutException extends RuntimeException {
    UpstreamTimeoutException(Throwable cause) {
        super("Upstream timeout", cause);
    }
}

class SystemFaultException extends RuntimeException {
    SystemFaultException(String privateDetail) {
        super(privateDetail);
    }
}

@RestController
@RequestMapping("/api")
class WidgetController {
    private final AtomicLong ids = new AtomicLong(100);
    private final Map<Long, Widget> widgets = new ConcurrentHashMap<>();

    @GetMapping(path = "/widgets/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<Widget> get(@PathVariable @Min(1) long id) {
        return Mono.defer(() -> {
            Widget widget = widgets.get(id);
            return widget != null
                    ? Mono.just(widget)
                    : Mono.error(new WidgetNotFoundException());
        });
    }

    @PostMapping(path = "/widgets",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<Widget>> create(
            @Valid @RequestBody CreateWidgetRequest request) {
        return Mono.fromSupplier(() -> {
            long id = ids.incrementAndGet();
            Widget widget = new Widget(id, request.name());
            widgets.put(id, widget);
            URI location = URI.create("/api/widgets/" + id);
            return ResponseEntity.created(location).body(widget);
        });
    }

    @GetMapping("/demo/conflict")
    Mono<String> conflict() {
        return Mono.error(new WidgetConflictException());
    }

    @GetMapping("/demo/timeout")
    Mono<String> timeout() {
        return Mono.delay(Duration.ofMillis(300))
                .map(tick -> "late")
                .timeout(Duration.ofMillis(40))
                .onErrorMap(TimeoutException.class,
                        UpstreamTimeoutException::new);
    }

    @GetMapping("/demo/crash")
    Mono<String> crash() {
        return Mono.error(new SystemFaultException(
                "jdbc-password=super-secret-value"));
    }
}

@Order(-1)
@RestControllerAdvice
class WidgetApiErrors {

    @ExceptionHandler(WidgetNotFoundException.class)
    ProblemDetail missing(WidgetNotFoundException ex) {
        return problem(HttpStatus.NOT_FOUND,
                "WIDGET_NOT_FOUND", "Không tìm thấy tài nguyên");
    }

    @ExceptionHandler(WidgetConflictException.class)
    ProblemDetail conflict(WidgetConflictException ex) {
        return problem(HttpStatus.CONFLICT,
                "WIDGET_CONFLICT",
                "Tài nguyên không ở trạng thái phù hợp");
    }

    @ExceptionHandler(UpstreamTimeoutException.class)
    ProblemDetail timeout(UpstreamTimeoutException ex) {
        return problem(HttpStatus.GATEWAY_TIMEOUT,
                "UPSTREAM_TIMEOUT",
                "Dịch vụ phụ trợ không phản hồi kịp thời");
    }

    @ExceptionHandler(SystemFaultException.class)
    ProblemDetail internal(SystemFaultException ex) {
        // Không trả ex.getMessage() cho HTTP client.
        return problem(HttpStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR", "Đã xảy ra lỗi hệ thống");
    }

    @ExceptionHandler(WebExchangeBindException.class)
    ProblemDetail invalidBody(WebExchangeBindException ex) {
        ProblemDetail p = problem(HttpStatus.BAD_REQUEST,
                "VALIDATION_FAILED", "Dữ liệu đầu vào không hợp lệ");
        p.setProperty("invalidFields",
                ex.getFieldErrors().stream()
                        .map(error -> error.getField())
                        .distinct()
                        .sorted()
                        .toList());
        return p;
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ProblemDetail invalidMethod(
            HandlerMethodValidationException ex) {
        HttpStatusCode status = ex.getStatusCode();
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                status,
                status.is4xxClientError()
                        ? "Dữ liệu đầu vào không hợp lệ"
                        : "Đã xảy ra lỗi hệ thống");
        p.setProperty("code", status.is4xxClientError()
                ? "VALIDATION_FAILED" : "INTERNAL_ERROR");
        return p;
    }

    private ProblemDetail problem(
            HttpStatusCode status, String code, String detail) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                status, detail);
        p.setProperty("code", code);
        return p;
    }
}
~~~

### 13.5. Giải thích code

- `@Valid @RequestBody CreateWidgetRequest` tạo validation errors theo WebFlux argument binding.
- `@Min(1)` trên path parameter là một method-level constraint, có thể gây `HandlerMethodValidationException`.
- Advice có `@Order(-1)` nhằm ưu tiên các handlers cụ thể hơn Boot RFC 9457 handler order 0.
- Không có `@ExceptionHandler(Exception.class)` để framework 405/415/406 vẫn hoạt động.
- `ProblemDetail.forStatusAndDetail` giữ status HTTP chính xác khi return directly từ handler.
- `setProperty("code")` tạo extension property được Jackson serialize top-level trong môi trường Spring chuẩn.
- `invalidFields` chỉ gồm safe names, không trả rejectedValue.
- `SystemFaultException` minh họa một exception message chứa secret, nhưng public body chỉ có detail generic.
- `HandlerMethodValidationException.getStatusCode()` giúp không biến return-value validation issue thành client 400.
- `Mono.defer` và `Mono.fromSupplier` tạo kết quả khi subscribe, nhưng map in-memory ở đây không thay database/transaction.
- `URI.create("/api/widgets/" + id)` là relative Location, không hardcode hostname nội bộ.
- `Duration.ofMillis(40)` là timeout rất ngắn dành riêng demo, không phù hợp production SLA.
- Demo chưa có authentication/authorization, quotas hoặc persistence; đây là ví dụ hạ tầng error handling.

### 13.6. Khởi chạy

~~~bash
mvn spring-boot:run
~~~

Tạo resource:

~~~bash
curl -i -X POST http://localhost:8080/api/widgets \
  -H 'Content-Type: application/json' \
  --data '{"name":"WebFlux course"}'
~~~

Với lần tạo đầu:

~~~http
HTTP/1.1 201 Created
Location: /api/widgets/101
Content-Type: application/json

{"id":101,"name":"WebFlux course"}
~~~

ID được tăng sau từng lần POST, đừng hardcode 101 trong integration tests.

Get theo Location:

~~~bash
curl -i http://localhost:8080/api/widgets/101
~~~

Resource 999999 thường chưa tồn tại:

~~~bash
curl -i http://localhost:8080/api/widgets/999999
~~~

Status 404, ProblemDetail tương đương:

~~~json
{
  "type":"about:blank",
  "title":"Not Found",
  "status":404,
  "detail":"Không tìm thấy tài nguyên",
  "instance":"/api/widgets/999999",
  "code":"WIDGET_NOT_FOUND"
}
~~~

JSON order không cố định; `instance` có thể được framework bổ sung.

### 13.7. Kiểm validation

~~~bash
curl -i -X POST http://localhost:8080/api/widgets \
  -H 'Content-Type: application/json' \
  --data '{"name":""}'
~~~

Kỳ vọng 400 và các fields:

~~~json
{
  "status":400,
  "detail":"Dữ liệu đầu vào không hợp lệ",
  "code":"VALIDATION_FAILED",
  "invalidFields":["name"]
}
~~~

Đây là trích đoạn, response thực còn type/title/instance. Path validation:

~~~bash
curl -i http://localhost:8080/api/widgets/0
~~~

Kỳ vọng 400 với code `VALIDATION_FAILED`.

### 13.8. Lỗi domain và hệ thống

~~~bash
curl -i http://localhost:8080/api/demo/conflict
curl -i http://localhost:8080/api/demo/timeout
curl -i http://localhost:8080/api/demo/crash
~~~

| Endpoint | HTTP status | code |
| --- | --- | --- |
| `/api/demo/conflict` | 409 | `WIDGET_CONFLICT` |
| `/api/demo/timeout` | 504 | `UPSTREAM_TIMEOUT` |
| `/api/demo/crash` | 500 | `INTERNAL_ERROR` |

Public body của 500 không được chứa `jdbc-password=super-secret-value`.

### 13.9. Lỗi built-in của framework

~~~bash
curl -i -X DELETE http://localhost:8080/api/widgets/101
curl -i -X POST http://localhost:8080/api/widgets \
  -H 'Content-Type: text/plain' \
  --data 'plain text'
curl -i -X POST http://localhost:8080/api/widgets \
  -H 'Content-Type: application/json' \
  --data '{"name":'
~~~

Tương ứng kỳ vọng HTTP 405, 415 và 400; error body sẽ do Boot/framework xử lý, không phải generic `INTERNAL_ERROR`.

## 14. WebTestClient kiểm thử

Tạo `src/test/java/demo/WebFluxProblemTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WebFluxProblemTest {

    @Autowired
    WebTestClient http;

    @Test
    void createReturns201AndLocation() {
        http.post().uri("/api/widgets")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateWidgetRequest("Reactive"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().valueMatches(
                        HttpHeaders.LOCATION,
                        "/api/widgets/[0-9]+")
                .expectBody()
                .jsonPath("$.name").isEqualTo("Reactive");
    }

    @Test
    void missingReturnsProblem404() {
        http.get().uri("/api/widgets/999999").exchange()
                .expectStatus().isNotFound()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.code").isEqualTo("WIDGET_NOT_FOUND");
    }

    @Test
    void invalidJsonBodyReturnsSafe400() {
        http.post().uri("/api/widgets")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateWidgetRequest(""))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_FAILED")
                .jsonPath("$.invalidFields[0]").isEqualTo("name");
    }

    @Test
    void pathConstraintIs400() {
        http.get().uri("/api/widgets/0").exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_FAILED");
    }

    @Test
    void domainConflictIs409() {
        http.get().uri("/api/demo/conflict").exchange()
                .expectStatus().isEqualTo(409)
                .expectBody()
                .jsonPath("$.code").isEqualTo("WIDGET_CONFLICT");
    }

    @Test
    void timeoutIs504() {
        http.get().uri("/api/demo/timeout").exchange()
                .expectStatus().isEqualTo(504)
                .expectBody()
                .jsonPath("$.code").isEqualTo("UPSTREAM_TIMEOUT");
    }

    @Test
    void serverErrorDoesNotLeakSecret() {
        http.get().uri("/api/demo/crash").exchange()
                .expectStatus().is5xxServerError()
                .expectBody(String.class)
                .value(body -> {
                    assertNotNull(body);
                    assertFalse(body.contains("jdbc-password"));
                    assertFalse(body.contains("super-secret-value"));
                });
    }

    @Test
    void frameworkMethodErrorStill405() {
        http.delete().uri("/api/widgets/42").exchange()
                .expectStatus().isEqualTo(405);
    }

    @Test
    void unsupportedMediaTypeStill415() {
        http.post().uri("/api/widgets")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("text")
                .exchange()
                .expectStatus().isEqualTo(415);
    }

    @Test
    void malformedJsonIs400() {
        http.post().uri("/api/widgets")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Tests dùng WebTestClient và Boot RANDOM_PORT để đi qua HTTP server, codecs, controller advice, validation và serialization thật; có giá trị hơn chỉ unit-test trực tiếp handler methods.

**Giới hạn:** đây là static sample, phải chạy Maven trên môi trường có dependencies để xác minh patch-version behavior. Nếu test validation/ProblemDetail content type sai, xem actual response và phiên bản Spring Boot/Framework trước khi sửa assertions. Không bỏ các negative tests chỉ để đạt green build.

## 15. ResponseEntityExceptionHandler vs Boot-first

Có hai cách phổ biến:

**Boot-first:**

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

Kèm một `@RestControllerAdvice` khai báo specific domain/validation handlers và giữ built-in 400/405/415 behavior cho Boot.

**Framework-first:** một advice extends WebFlux `ResponseEntityExceptionHandler` và tùy biến framework-specific protected hooks theo Spring Framework 6.2 Javadoc.

Không thêm cả hai theo kiểu "bắt cho chắc" khi chưa có thiết kế ordering, vì có thể duplicate handling và khác message codes.

### 15.1. i18n với MessageSource

`ErrorResponse`/`ResponseEntityExceptionHandler` hỗ trợ message codes cho type/title/detail, được resolve qua `MessageSource`. Có thể dịch detail cho tiếng Việt/tiếng Anh nhưng giữ `code=VALIDATION_FAILED` không đổi.

Tránh dùng exception message làm translation key chưa sanitize. Với validation, nội dung interpolated values phải được kiểm privacy.

### 15.2. ErrorResponse interceptor

Spring Framework 6.2 WebFlux documentation đề cập khả năng đăng ký `ErrorResponse` interceptors qua WebFlux Configurer để bổ sung hoặc ghi nhận RFC 9457 responses. Khi cần attach requestId/correlation chung, cân nhắc official extension points; không phải lúc nào cũng cần tự viết low-level `WebExceptionHandler`.

## 16. Các lỗi phổ biến

1. Dùng generic catch-all `Exception.class` ở advice priority cao rồi làm mọi 400/405/415 thành 500.
2. Trả ProblemDetail.status 404 nhưng HTTP response status line là 200.
3. Lấy `ex.getMessage()` cho 500, vô tình lộ SQL/credentials.
4. Chỉ bắt WebExchangeBindException mà không biết HandlerMethodValidationException.
5. Ép mọi method validation exception thành 400 dù có return-value validation.
6. Dùng MVC Servlet exception handler signatures trong WebFlux.
7. Tin @RestControllerAdvice bắt mọi lỗi ở WebFilter/Spring Security/gateway.
8. Tin advice có thể đổi status sau khi SSE response committed.
9. Xem cancellation của client là onError luôn luôn.
10. Đặt quá nhiều domain logic/status trực tiếp trong @ResponseStatusException ở service.
11. Tái sử dụng mutable ProblemDetail instance chung giữa requests.
12. Trả rejected password/token values trong validation errors.
13. Dùng raw query/Host header tạo problem type/instance.
14. Thêm @EnableWebFlux trong Boot chỉ để “bật WebFlux”, vô tình vô hiệu hóa auto-config ProblemDetails.
15. Không test built-in 405/406/415 sau khi thêm global advice.
16. Dùng blocking I/O trong error handler trên Reactor Netty event-loop.
17. Gọi subscribe() trong controller làm errors thoát HTTP lifecycle.
18. Nuốt mọi lỗi bằng onErrorResume/onErrorComplete rồi trả 200 success.
19. Lạm dụng @Order để che conflict thay vì thiết kế loại exception riêng.
20. Coi HTTP 499 của proxy là chuẩn WebFlux phải gửi.
21. Coi `detail` là error code ổn định cho frontend.
22. Thêm requestId vào metric labels gây high cardinality.
23. Cho rằng bật Boot ProblemDetails có thể chỉnh mọi 401/403/Security error.
24. Không quản lý thông tin nhạy cảm trong logs dù public payload đã redact.
25. Không có integration tests cho JSON codecs, content negotiation và handler order.

## 17. Debug theo triệu chứng

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm |
| --- | --- | --- |
| Invalid DTO trả 500 | Catch-all hoặc mapping sai | WebExchangeBindException, advice ordering |
| @Min không chạy | Method validation chưa active/signature khác | Jakarta provider, Boot/Framework, annotations |
| Trả 400 cho return-value invalid | Bắt HandlerMethodValidationException và hardcode 400 | ex.getStatusCode |
| @RestControllerAdvice không chạy | Sai component scan/scope hoặc lỗi ở filter | basePackages, order, WebFilter |
| 404 body khác các lỗi domain | Route not found qua Boot fallback | ControllerAdvice vs error handler |
| POST text/plain trả 500 | Generic handler nuốt UnsupportedMediaType | 415 defaults |
| code không ở top-level | Jackson ProblemDetail mixin bị thay đổi | Codecs, content type |
| ProblemDetails property không hiệu quả | Boot WebFlux auto-config không còn active | @EnableWebFlux, app type, property |
| CORS/Security 401/403 khác | Security filter layer | ServerHttpSecurity / gateway policy |
| WebClient error body lộ hostname | Raw upstream error được echo | Domain translation, redaction |
| SSE lỗi sau 200 không có ProblemDetail 500 | Response đã committed | In-band error hoặc cleanup |
| Timeout 500 thay vì 504 | Chưa map TimeoutException | onErrorMap/domain advice |
| Test controller unit pass nhưng HTTP fail | Bỏ qua codec/validation/error resolver | WebTestClient HTTP integration |

## 18. Bài tập

**Bài 1.** Tạo local @ExceptionHandler và global @RestControllerAdvice cùng xử lý WidgetNotFoundException. Handler nào chạy? Khi nào nên giữ một chỗ duy nhất?

**Bài 2.** Tạo ProblemDetail 409 với type, title, detail, instance, code; kiểm HTTP status line trùng status trong body.

**Bài 3.** Viết DTO có @NotBlank và @Size, bật starter-validation, trả invalidFields nhưng không trả rejected password.

**Bài 4.** Gắn @Min lên @PathVariable; phân biệt WebExchangeBindException và HandlerMethodValidationException.

**Bài 5.** Một return-value method constraint sai. Vì sao mặc định có thể là HTTP 500 thay vì 400?

**Bài 6.** Bật spring.webflux.problemdetails.enabled và kiểm 405/415/400. Tại sao @EnableWebFlux có thể làm behavior khác Boot defaults?

**Bài 7.** Hai advice khác @Order; một handler match cause, một match root. Trình bày quy tắc precedence.

**Bài 8.** Dùng onErrorMap để chuyển TimeoutException thành UpstreamTimeoutException; map sang ProblemDetail 504 với error code.

**Bài 9.** Một WebFilter tự phát lỗi. Vì sao controller advice có thể không xử lý? Tầng nào phù hợp?

**Bài 10.** Browser hủy SSE sau khi nhận 200 và vài events. Tại sao không thể gửi JSON 500 mới? Khi nào in-band app-error event có ích?

**Bài 11.** Xây catalog domain error codes cho 400, 404, 409, 429, 503; mô tả versioning và backward compatibility của extensions.

**Bài 12.** Thiết kế requestId/traceId cho public error body và logging, với privacy/correlation validation.

**Bài 13.** Thêm reactive Spring Security. Xác minh 401/403 thuộc error handler nào và CORS/CSRF phối hợp ra sao.

**Bài 14.** Viết WebTestClient kiểm create, validation, missing, conflict, timeout, 500 redaction, 405 và 415.

**Bài 15.** Dịch title/detail sang hai locale nhưng không đổi status/type/code; kiểm clients vẫn xử lý được.

## 19. Checklist production

- [ ] Hợp đồng RFC 9457 ProblemDetail nhất quán và có docs.
- [ ] Status line, ProblemDetail.status và domain code không mâu thuẫn.
- [ ] Local/global advice có phân công rõ và ordering được kiểm bằng tests.
- [ ] Không có catch-all ưu tiên cao phá Spring built-in errors.
- [ ] Boot ProblemDetails config không conflict với custom ResponseEntityExceptionHandler.
- [ ] Hai loại validation exception được xử lý hoặc được Boot xử lý đúng.
- [ ] Lỗi method return validation không bị trả thành 400 client.
- [ ] Không public secrets/stacktraces/raw rejected values.
- [ ] Logs có correlation ID và privacy controls, metrics tránh high cardinality.
- [ ] 401/403 của Security được kiểm ở đúng reactive filter layer.
- [ ] 404/405/406/415/429/500/503/504 semantics được kiểm.
- [ ] Streaming post-commit errors dùng SSE event/cancel, không gửi HTTP response mới.
- [ ] Client cancellation và Reactor onError được phân biệt.
- [ ] Errors từ WebFilter/WebClient/gateway có contract rõ.
- [ ] Code/type ổn định qua locale và version; extensions additive.
- [ ] WebTestClient integration tests chạy trong CI, có negative cases.
- [ ] Không blocking Netty event-loop trong exception handler.
- [ ] Production authentication, authorization, CSRF, CORS và deployment proxy policy đã được kiểm.

## 20. Tổng kết

- `@ExceptionHandler` xử lý lỗi tại annotated controller, `@RestControllerAdvice` dùng chung giữa controllers.
- `ProblemDetail` theo RFC 9457 cung cấp các fields type/title/status/detail/instance và có thể mở rộng code/requestId.
- `ResponseEntityExceptionHandler` hỗ trợ framework ErrorResponse; Spring Boot WebFlux có property bật Problem Details.
- `WebExchangeBindException` và `HandlerMethodValidationException` phục vụ hai phạm vi validation khác nhau; không hardcode mọi method validation thành 400.
- Local advice, global advice, `@Order` và root/cause matching quyết định handler được chọn.
- WebFilter, Security, gateway và response đã committed nằm ngoài lời hứa “mọi lỗi đều qua @RestControllerAdvice”.
- Reactor cancellation không phải onError; lỗi business khi stream đã committed cần protocol xử lý in-band hoặc cleanup.
- API lỗi phải có đúng status, safe message, mã ổn định và tests regression; không leak internal exception messages.

## 21. Tài liệu tham khảo

- [Spring Framework 6.2 — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html).
- [Spring Framework 6.2 — WebFlux Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-advice.html).
- [Spring Framework 6.2 — Controller Exception Handling](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-exceptions.html).
- [Spring Framework 6.2 — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html).
- [Spring Framework 6.2 — ResponseEntityExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html).
- [Spring Framework 6.2 — ProblemDetail API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ProblemDetail.html).
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html).
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457).
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html).

# Annotated controller và functional endpoint trong Spring WebFlux

## 1. Hai cách khai báo cùng một REST API

Trong Spring WebFlux, cùng endpoint **GET /api/orders/{id}** có thể được viết bằng **@RestController + @GetMapping** hoặc **RouterFunction + HandlerFunction**. Cả hai cùng xử lý HTTP và có thể gọi chung service phản ứng. Khác biệt nằm ở **cách định tuyến, bind tham số, validation, tổ chức lỗi và điểm mở rộng**.

Đổi sang functional **không tự tăng hiệu năng** hay sửa lỗi JDBC blocking, phân quyền, retry tạo trùng.

Bài thuộc chương **Spring WebFlux**, module **INTEGRATION_API_REST**, liên hệ resource/URI, HTTP methods/status, data contract, phân trang, cache, idempotency, OpenAPI, security và Java/Spring.

**Mục tiêu:** triển khai Orders API bằng cả hai phong cách; hiểu Reactor và lifecycle HTTP; trả đúng 200/201/400/401/403/404/422; xử lý validation, security, cancellation và kiểm thử bằng WebTestClient.

## 2. Request lifecycle và mô hình reactive

Ứng dụng Spring Boot 3 với WebFlux trên **Reactor Netty** thường đi qua:

~~~mermaid
flowchart TD
    A["HTTP client"] --> B["Reactor Netty / HTTP server"]
    B --> C["WebFilter chain / Spring Security"]
    C --> D["DispatcherHandler"]
    D --> E{"Chọn HandlerMapping"}
    E --> F["@RequestMapping annotated controller"]
    E --> G["RouterFunction request predicates"]
    F --> H["Argument resolver + controller"]
    G --> I["HandlerFunction ServerRequest"]
    H --> J["Mono / Flux từ service"]
    I --> J
    J --> K["Encoder / HTTP response"]
    K --> A
~~~

WebFlux cũng chạy trên Servlet async, **không bắt buộc Netty**. Khi có cả **starter-web** và **starter-webflux**, kiểm tra application type; thêm dependency không tự biến MVC thành WebFlux.

### 2.1. Mono và Flux

| Kiểu Reactor | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Mono<T>** | 0 hoặc 1 kết quả, complete hoặc error. | GET một order, tạo order, HTTP response. |
| **Flux<T>** | Nhiều kết quả có thể phát dần. | Collection, sự kiện SSE. |
| **Mono<Void>** | Hoàn thành hoặc lỗi, không có value. | Một command không cần body. |
| **Mono<ServerResponse>** | Trả status/headers/body kiểu functional. | HandlerFunction cho GET/POST. |

**Không tự subscribe() trong controller/handler**. WebFlux subscribe vào publisher trả về để quản lý lifecycle HTTP. Tự subscribe có thể gây side effect chạy ngoài response, mất cancellation, error handling, security context và transaction.

Reactive **không tự song song**; hiệu suất phụ thuộc I/O và scheduler. JDBC trên event-loop vẫn chặn thread.

### 2.2. Chuỗi reactive và lỗi

~~~text
request
  -> Security / routing
  -> đọc JSON, kiểm tra input
  -> service trả Mono/Flux
  -> map / flatMap để dựng response
  -> encode HTTP body
  -> complete, error hoặc cancel
~~~

**map** biến đổi đồng bộ, **flatMap** nối publisher, **switchIfEmpty** xử lý rỗng, **onErrorResume** xử lý lỗi có chủ đích; không đổi mọi lỗi DB thành 200/404.

## 3. Một hợp đồng HTTP cho cả hai kiểu endpoint

| Operation | Request | Response |
| --- | --- | --- |
| Đọc đơn | **GET /api/orders/{id}** với Bearer có quyền đọc | 200 JSON; 401/403 thiếu quyền; 404 không thấy. |
| Tạo đơn | **POST /api/orders**, JSON CreateOrder, Bearer có quyền ghi | 201 Created + Location + JSON; 400/422 input không hợp lệ. |
| Liệt kê | **GET /api/orders?limit=20&cursor=...** | 200 trang dữ liệu, cursor opaque; không stream vô hạn. |

Ví dụ:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json

{"customerId":"22222222-2222-4222-8222-222222222222","totalMinorUnit":125000}

HTTP/1.1 201 Created
Location: /api/orders/11111111-1111-4111-8111-111111111111
Content-Type: application/json

{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "CREATED",
  "totalMinorUnit": 125000,
  "note": null
}
~~~

Request và response ở trên là **hai thông điệp liên tiếp**, đặt chung để dễ đọc. Hai bản code tiếp theo là **phương án thay thế** cho cùng URI. **Không đăng ký đồng thời hai GET/POST mappings** trong cùng ứng dụng; hãy chọn một phương án bằng cấu hình/profile để tránh xung đột hoặc route ưu tiên không như dự tính.

## 4. DTO và service chung

~~~java
import java.util.UUID;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import reactor.core.publisher.Mono;

record CreateOrder(
        @NotNull UUID customerId,
        @NotNull @PositiveOrZero Long totalMinorUnit,
        String note) {}

record OrderView(
        UUID id, String status, long totalMinorUnit, String note) {}

interface OrderService {
    Mono<OrderView> findAuthorized(String actor, UUID orderId);
    Mono<OrderView> createAuthorized(String actor, CreateOrder command);
}

class OrderNotFoundException extends RuntimeException {}
~~~

Service phải kiểm **tenant, số tiền, idempotency và commit**. Annotation DTO không thay business validation. **Long** phân biệt JSON thiếu field với 0; lưu ý miền số JavaScript.

Service có thể dùng **Spring Data R2DBC** hoặc reactive HTTP client. Đổi kiểu trả về thành Mono **không biến JDBC/JPA bên dưới thành non-blocking**.

## 5. Phong cách 1 — Annotated controller

WebFlux hỗ trợ **@RestController, @GetMapping, @PostMapping, @PathVariable, @RequestBody, @Valid** như các ứng dụng Spring quen thuộc, nhưng method có thể trả publisher:

~~~java
import java.net.URI;
import java.security.Principal;
import java.util.UUID;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
class OrdersAnnotatedController {
    private final OrderService service;

    OrdersAnnotatedController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderView>> get(
            @PathVariable UUID id, Principal principal) {
        return service.findAuthorized(principal.getName(), id)
                .map(ResponseEntity::ok)
                .switchIfEmpty(Mono.error(
                        new OrderNotFoundException()));
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<OrderView>> create(
            @Valid @RequestBody Mono<CreateOrder> input,
            Principal principal) {
        return input
                .flatMap(command -> service.createAuthorized(
                        principal.getName(), command))
                .map(order -> ResponseEntity
                        .created(URI.create(
                                "/api/orders/" + order.id()))
                        .body(order));
    }
}
~~~

**Lưu ý:** @Valid với reactive body cần Bean Validation provider và mapping lỗi 400/422; Principal giả định route yêu cầu xác thực. Mono.empty() của GET thành lỗi not-found; 201/Location chỉ sau khi tạo thành công. Collection lớn nên phân trang, không collectList() vô hạn.

**Annotation phù hợp** cho binding DTO, validation, ControllerAdvice, OpenAPI tooling quen thuộc. Trả Mono không chứng minh I/O non-blocking.

## 6. Phong cách 2 — Functional endpoint

WebFlux.fn dùng **RouterFunction** để ghép **request predicate** với **HandlerFunction**. Handler nhận **ServerRequest** và trả **Mono<ServerResponse>**; code chủ động đọc request, validate, gọi service và xây response.

### 6.1. Đăng ký RouterFunction

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
class OrdersFunctionalRoutes {
    @Bean
    RouterFunction<ServerResponse> ordersRouter(
            OrdersHandler handler) {
        return RouterFunctions.route()
                .GET("/api/orders/{id}", handler::get)
                .POST("/api/orders", handler::create)
                .build();
    }
}
~~~

RequestPredicate xét method/path/header/media type. Predicate không khớp có thể thành **404 thay vì 415** khi Content-Type sai; mẫu này kiểm tra trong handler.

### 6.2. Handler đọc input và dựng status rõ ràng

~~~java
import java.net.URI;
import java.util.UUID;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebInputException;
import reactor.core.publisher.Mono;

@Component
class OrdersHandler {
    private final OrderService service;
    private final Validator validator;

    OrdersHandler(OrderService service, Validator validator) {
        this.service = service;
        this.validator = validator;
    }

    Mono<ServerResponse> get(ServerRequest request) {
        UUID id;
        try {
            id = UUID.fromString(request.pathVariable("id"));
        } catch (IllegalArgumentException ex) {
            return ServerResponse.badRequest().build();
        }

        return request.principal()
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.UNAUTHORIZED)))
                .flatMap(principal -> service.findAuthorized(
                        principal.getName(), id))
                .flatMap(order -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(order))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    Mono<ServerResponse> create(ServerRequest request) {
        boolean isJson = request.headers().contentType()
                .map(MediaType.APPLICATION_JSON::isCompatibleWith)
                .orElse(false);
        if (!isJson) {
            return ServerResponse
                    .status(HttpStatus.UNSUPPORTED_MEDIA_TYPE)
                    .build();
        }

        return request.principal()
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.UNAUTHORIZED)))
                .flatMap(principal -> request
                        .bodyToMono(CreateOrder.class)
                        .switchIfEmpty(Mono.error(
                                new ServerWebInputException(
                                        "Request body required")))
                        .flatMap(command -> {
                            var violations = validator.validate(command);
                            if (!violations.isEmpty()) {
                                return Mono.error(
                                        new ConstraintViolationException(
                                                violations));
                            }
                            return service.createAuthorized(
                                    principal.getName(), command);
                        }))
                .flatMap(order -> ServerResponse
                        .created(URI.create(
                                "/api/orders/" + order.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(order));
    }
}
~~~

**Khác annotation:** Handler tự parse UUID (400), kiểm Content-Type (415), đọc body và dựng ServerResponse. Jakarta Validation không tự chạy trên DTO functional nên gọi Validator thủ công. **Không block()/subscribe()**; nhánh principal trống không thay Security entry point.

**Functional phù hợp** cho routing tường minh/filter theo route; validation/error/OpenAPI cần khai báo chủ động.

### 6.3. Dùng chung HTTP contract

Annotated dùng argument resolver, functional tự parse nhiều bước; **cả hai phải giống status, Content-Type, Location, validation và quyền**, không chỉ schema JSON.

## 7. So sánh hai phong cách trong quyết định thiết kế

| Góc nhìn | Annotated | Functional |
| --- | --- | --- |
| Route/input | @GetMapping, @PathVariable, @RequestBody. | RouterFunction, ServerRequest. |
| Response | ResponseEntity / publisher. | Mono<ServerResponse>. |
| Validation/lỗi | @Valid, ControllerAdvice. | Validator, HandlerFilterFunction/WebExceptionHandler. |
| Tooling/test | Annotation-based OpenAPI, bindToController. | Contract khai báo chủ động, bindToRouterFunction. |
| I/O | Cùng rủi ro blocking trên event loop. | Cùng rủi ro blocking trên event loop. |

Nhất quán coding style và testability quan trọng hơn cú pháp; không kiểu nào tự non-blocking hơn.

### 7.1. Route ordering và fallback

Functional route xét theo thứ tự/nest; đặt route cụ thể trước wildcard. Annotated mapping có quy tắc specificity riêng và có thể báo ambiguous mapping. **Không đăng ký trùng GET URI**.

### 7.2. Đừng biến response rỗng thành sai HTTP

**Mono.empty()** khi GET một resource nên thành **404** theo policy; POST tạo phải trả ID/Location khi thành công. DELETE có thể trả **204 không body**; collection rỗng vẫn có thể **200 với danh sách rỗng**. Phân biệt Mono<ResponseEntity<T>> và ResponseEntity<Flux<T>>: khi đã commit streaming headers, lỗi giữa body không thể thay thành JSON 500 mới.

## 8. WebFilter, HandlerFilterFunction và Spring Security

| Thành phần | Phạm vi | Phù hợp cho |
| --- | --- | --- |
| **WebFilter** | WebFlux exchange trước và xung quanh routing. | Correlation ID, trace, header kỹ thuật, xử lý cross-cutting ở HTTP layer. |
| **HandlerFilterFunction** | Các handler của RouterFunction nơi filter được gắn. | Timing/logic tùy nhóm functional route, map lỗi domain đã được phát từ handler. |
| **SecurityWebFilterChain** | Tầng Spring Security WebFlux, trước endpoint. | Bearer JWT, scope, CSRF/CORS policy, authentication/authorization ở request. |
| **Service/domain authorization** | Tài nguyên và luật nghiệp vụ. | Actor có được phép xem/sửa order cụ thể không. |

**WebFilter không phải Servlet Filter/HandlerInterceptor của Spring MVC**. WebFlux functional filter không tự áp cho controller annotation, và ControllerAdvice của annotated controller không phải cách thống nhất tự động xử lý tất cả lỗi từ functional handlers.

### 8.1. Security cho cả annotated lẫn functional

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class OrdersWebFluxSecurity {
    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers("/public/health").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders")
                        .hasAuthority("SCOPE_orders.write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth -> oauth.jwt(
                        Customizer.withDefaults()))
                .build();
    }
}
~~~

**Giả định bảo mật của mẫu:** API chỉ dùng **Bearer token từ Authorization header**, không dựa vào cookie/session xác thực ở trình duyệt. Vì vậy mẫu tắt CSRF cho kiểu client đó; **không copy quy tắc này sang ứng dụng dùng cookie/session**. Cần cấu hình JWT issuer/JWK, CORS và giới hạn origin/headers theo môi trường.

Security route matcher kiểm quyền **đọc/ghi cấp endpoint**. Service vẫn phải kiểm **owner/tenant** theo identity đáng tin; UUID khó đoán hoặc biết URL chưa tạo ra quyền. **401** dùng cho chưa xác thực, **403** cho đã xác thực nhưng không đủ quyền; với resource của tenant khác, chính sách có thể trả 403 hoặc 404 để không tiết lộ sự tồn tại.

### 8.2. Correlation ID trong WebFilter

~~~java
import java.util.UUID;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.server.WebFilter;

@Configuration
class CorrelationConfig {
    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE + 10)
    WebFilter correlationIdWebFilter() {
        return (exchange, chain) -> {
            String supplied = exchange.getRequest()
                    .getHeaders().getFirst("X-Request-ID");
            String id = supplied != null
                    && supplied.matches("[A-Za-z0-9_-]{1,64}")
                    ? supplied : UUID.randomUUID().toString();

            exchange.getResponse().getHeaders()
                    .set("X-Request-ID", id);
            return chain.filter(exchange)
                    .contextWrite(context ->
                            context.put("requestId", id));
        };
    }
}
~~~

Filter gắn header **trước** chain và bỏ qua input ID không an toàn. **Reactor Context không tự đồng nghĩa với SLF4J MDC**: log correlation trên nhiều thread cần tích hợp context propagation/tracing phù hợp. Kiểm thử thứ tự filter với Security thật để bảo đảm cả phản hồi 401/403 cũng có request ID.

### 8.3. Filter lỗi chỉ cho functional router

Một RouterFunction có thể dùng HandlerFilterFunction để map lỗi domain:

~~~java
RouterFunctions.route()
    .GET("/api/orders/{id}", handler::get)
    .POST("/api/orders", handler::create)
    .filter((request, next) -> next.handle(request)
        .onErrorResume(OrderNotFoundException.class, ex -> {
            var problem = org.springframework.http.ProblemDetail
                .forStatusAndDetail(
                    org.springframework.http.HttpStatus.NOT_FOUND,
                    "Không tìm thấy đơn hàng.");
            return ServerResponse
                .status(org.springframework.http.HttpStatus.NOT_FOUND)
                .contentType(org.springframework.http.MediaType
                    .APPLICATION_PROBLEM_JSON)
                .bodyValue(problem);
        }))
    .build();
~~~

Đây là **đoạn minh họa thay thế bean RouterFunction ở phần 6**, không đăng ký thêm một router trùng. Filter này chỉ bắt **lỗi phát từ handler sau khi route match**; 401 từ Security, 404 do không match route hoặc lỗi trước handler có pipeline riêng. Functional validation error như ConstraintViolationException cũng cần handler **400/422** theo contract thay vì mặc định thành 500.

## 9. Validation và lỗi HTTP nhất quán

### 9.1. Annotated ControllerAdvice

~~~java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class OrderProblems {
    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound() {
        ProblemDetail detail = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Không tìm thấy đơn hàng.");
        detail.setType(URI.create(
                "https://api.example.com/problems/order-not-found"));
        detail.setTitle("Order not found");
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(detail);
    }
}
~~~

Trong annotated pipeline, ControllerAdvice có thể xử lý lỗi từ controller/argument resolution theo cơ chế MVC-like của WebFlux. Ở functional pipeline, dùng **HandlerFilterFunction** hoặc **WebExceptionHandler/ErrorWebExceptionHandler** phù hợp. Với Security, cấu hình authentication entry point/access denied handler nếu phải trả **Problem Details** thay vì response mặc định.

### 9.2. Map lỗi theo nguyên nhân, không theo phong cách code

| Tình huống | Status |
| --- | --- |
| Chưa xác thực / thiếu scope | **401** (WWW-Authenticate khi phù hợp) / **403**. |
| UUID, JSON sai / media type sai | **400** / **415**. |
| Vi phạm validation nghiệp vụ | **400/422** theo hợp đồng. |
| Resource không có hoặc được che | **404**. |
| Tạo thành công | **201 + Location**. |
| DB/timeout downstream lỗi | **5xx** phù hợp, không biến thành 404. |

**Problem Details theo RFC 9457** giúp chuẩn hóa type/title/status/detail, nhưng framework mặc định và handler tự viết có thể phát JSON khác nhau. Hãy kiểm tra cả **Content-Type: application/problem+json**, status thực tế, schema và hành vi security ở gateway.

## 10. I/O không chặn, backpressure và tác dụng phụ

### 10.1. Không block event loop

Tránh trong annotated và functional handler:

~~~java
// Sai trên event-loop: chặn thread để chờ reactive result.
OrderView order = service.findAuthorized(actor, id).block();

// Sai khi gọi JDBC/JPA hoặc Thread.sleep trực tiếp trong map.
Mono.just(id).map(x -> legacyRepository.findById(x));
~~~

Nên giữ các bước non-blocking từ HTTP đến storage:

~~~java
Mono<OrderView> result = reactiveRepository.findById(id)
        .flatMap(entity -> authorization.checkAndMap(actor, entity));
~~~

Đây là **giả mã phụ thuộc repository/service chưa cung cấp**. Khi phải tích hợp thư viện blocking cũ, có thể cô lập tạm bằng **Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())** cùng timeout/quota; đây không biến JDBC thành reactive, cũng không giải quyết connection pool, transaction hay khả năng mở rộng vô hạn. Không dùng scheduler chuyển thread như biện pháp che sự cố hiệu năng.

### 10.2. Backpressure không thay phân trang và giới hạn

Flux có cơ chế demand, nhưng response JSON dạng một array có thể khiến serialization/buffering khác với NDJSON hoặc **text/event-stream**. Nếu client mở SSE vô hạn, cần chính sách heartbeat, max concurrent streams, cancellation, buffer bounds và authentication/authorization trên mỗi kết nối.

GET collection thông thường nên công bố **limit/cursor**, kích thước trang tối đa và cách xử lý thay đổi dữ liệu; không dùng Flux vô hạn để bỏ qua contract phân trang. Với download file, áp giới hạn DataBuffer/codecs, streaming, kích thước request và backpressure của nguồn.

### 10.3. Cancellation, timeout và retry

Client ngắt kết nối có thể khiến subscription bị **cancel**. Cancellation không có nghĩa một giao dịch hoặc external side effect đã chắc chắn rollback. Với POST tạo đơn/thanh toán:

- Dùng **Idempotency-Key** và ràng buộc dữ liệu nguyên tử để ngăn double submit khi client retry sau timeout.
- Không tự gọi **retry()** lên mọi Mono ghi dữ liệu, nhất là sau lỗi mạng không biết server đã commit hay chưa.
- Timeout phải phản ánh ngân sách request và downstream, không chỉ thêm toán tử timeout mà quên xử lý giao dịch, error mapping và resource cleanup.
- Transaction reactive sử dụng **Reactor Context**; không gọi subscribe() rời pipeline hoặc giả định transaction ThreadLocal của JPA áp dụng nguyên xi.

Một ví dụ gọi downstream với WebClient:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

Mono<OrderView> getRemote(
        WebClient client, String orderId) {
    return client.get()
            .uri("/internal/orders/{id}", orderId)
            .retrieve()
            .bodyToMono(OrderView.class)
            .timeout(Duration.ofSeconds(3));
}
~~~

WebClient **retrieve()** mặc định phát error signal cho 4xx/5xx; muốn chuyển 404 thành lỗi domain, cấu hình onStatus/onErrorMap có chủ đích. Đặt base URL, TLS, timeout kết nối, pool, auth propagation và giới hạn retry ở cấu hình production. Không chuyển token của người dùng sang host không tin cậy.

## 11. Kiểm thử contract với WebTestClient

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| T01 | GET đúng ID và có quyền | **200**, Order JSON đúng, không lộ tenant khác. |
| T02 | GET UUID sai | **400**; không biến thành 500. |
| T03 | GET không có order | **404** theo chính sách. |
| T04 | POST JSON hợp lệ | **201**, Location đúng, một order được commit. |
| T05 | POST thiếu field / totalMinorUnit âm | **400/422** theo hợp đồng, không có side effect. |
| T06 | POST Content-Type không hỗ trợ | **415** nhất quán ở cả hai phong cách. |
| T07 | Không token / thiếu scope / tenant khác | **401/403/404** theo policy, không lộ dữ liệu. |
| T08 | Service phát lỗi DB/timeout | Không bị nuốt thành 200 hay 404 sai. |
| T09 | Concurrent retry cùng Idempotency-Key | Không tạo order trùng; test với storage thật. |
| T10 | Client cancel stream / backpressure | Hủy nguồn, cleanup resource; không leak buffer. |

### 11.1. WebTestClient trên functional router

Ví dụ test nhánh UUID sai, không cần kết nối DB hoặc security:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

@Test
void invalidPathVariableIsBadRequest(
        @Autowired RouterFunction<ServerResponse> routes) {
    WebTestClient client =
            WebTestClient.bindToRouterFunction(routes).build();
    client.get()
            .uri("/api/orders/not-a-uuid")
            .exchange()
            .expectStatus().isBadRequest();
}
~~~

Đây là **đoạn test minh họa**, cần đưa vào fixture JUnit cung cấp routes/handler/service/validator. Bind-to-router test **không tự kiểm chứng SecurityWebFilterChain**, vì không chạy full application filter pipeline.

### 11.2. WebTestClient có WebFlux Security

Với **@SpringBootTest**, một test dùng application context có thể:

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .apply(org.springframework.security.test.web.reactive.server
                .SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();

client.get().uri("/api/orders/{id}", orderId)
        .mutateWith(org.springframework.security.test.web.reactive.server
                .SecurityMockServerConfigurers.mockJwt()
                .authorities(new org.springframework.security.core.authority
                        .SimpleGrantedAuthority("SCOPE_orders.read")))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(orderId.toString());
~~~

Đoạn này cần **spring-security-test**, context chỉ đăng ký **một** kiểu endpoint, và service fixture cung cấp order có quyền cho identity test. Bổ sung test thiếu token trả 401, thiếu scope 403; test tenant khác nên chạy **service/database thật** hoặc repository fixture kiểm soát được.

### 11.3. Test publisher và kết quả cuối

**StepVerifier** kiểm tra một publisher thành công, lỗi hoặc bị hủy; **WebTestClient** kiểm tra HTTP. Test đơn lẻ Mono thành công **không chứng minh transaction đã commit**, do đó cần integration test sau POST: query lại resource, kiểm tra Location, quyền và idempotency. Với streaming, kiểm tra cancellation và timeout trên server thật khi có thể.

## 12. Bài tập: chuyển Orders API từ MVC sang WebFlux

Hệ thống dùng **GET/POST /api/orders** với Spring MVC/JPA. Nhóm muốn dùng WebFlux vì cần đồng thời nhiều kết nối đọc trạng thái, nhưng vẫn giữ JDBC, JWT, cache và DTO cũ.

**Yêu cầu:** (1) Viết hai mapping GET theo annotated và RouterFunction. (2) Xác định chỗ tạo 404, 201/Location, validation và 415. (3) Nêu rủi ro giữ JDBC trên event-loop. (4) Thiết kế quyền order theo tenant và xử lý 401/403. (5) Đề xuất test chứng minh hai cách trả HTTP tương đương và không tạo trùng khi POST retry.

**Hướng giải:** cả hai gọi **OrderService** với Mono, nhưng cần driver/adapter I/O phù hợp; không chỉ bọc JDBC bằng Mono.just. Controller dùng @PathVariable/@RequestBody; functional dùng ServerRequest/bodyToMono và tự validate. Spring Security filter bảo vệ route, service kiểm tenant; error pipeline ánh xạ đúng Problem Details. Dùng WebTestClient cho status/schema và integration tests cho persistence, timeout, cancellation, idempotency.

## 13. Checklist và kết luận

- [ ] Chọn **annotated hoặc functional** cho cùng URI, không đăng ký hai handler cạnh tranh.
- [ ] Cả hai giữ chung HTTP contract: 200/201/400/401/403/404/415/422, Location, JSON và lỗi.
- [ ] Không block()/subscribe() trong request handler; kiểm tra I/O blocking và scheduler.
- [ ] Functional routes xử lý fallback predicate, input validation và exception mapping rõ ràng.
- [ ] Spring Security WebFilterChain kiểm JWT/scope; service kiểm quyền tenant/order.
- [ ] WebFilter và HandlerFilterFunction đúng phạm vi; Reactor Context không tự là MDC.
- [ ] Mono.empty(), error, cancel và streaming body được xử lý đúng HTTP semantics.
- [ ] WebTestClient kiểm route, security, Problem Details; integration test kiểm DB/side effects.
- [ ] Có giới hạn collection/stream, timeout, retry, memory và idempotency.

**Kết luận:** **Annotated controller** và **functional endpoint** là hai cách biểu đạt REST API trên cùng nền Spring WebFlux. Lựa chọn dựa trên độ rõ ràng của routing, validation/tooling và tổ chức code; tính đúng đến từ **HTTP contract nhất quán, service non-blocking, security thật và kiểm thử các luồng lỗi/cancellation**, chứ không nằm ở cú pháp annotation hay RouterFunction.

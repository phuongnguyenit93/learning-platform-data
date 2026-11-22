# Xử lý lỗi và Problem Details trong reactive stack

## 1. Vấn đề: lỗi HTTP không biến mất khi chuyển sang WebFlux

Trong **Spring WebFlux**, controller/service trả **Mono<T>** hoặc **Flux<T>**. Lỗi phát sinh lúc đọc body, kiểm tra quyền, gọi DB/downstream hoặc stream dữ liệu; API phải giữ đúng **ngữ nghĩa HTTP** và **vòng đời reactive**.

Ví dụ client đọc đơn:

~~~http
GET /api/orders/ord-42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Nếu đơn không tồn tại hoặc bị che giấu theo chính sách, API có thể trả:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Không tìm thấy đơn có thể truy cập",
  "instance": "/api/orders/ord-42",
  "code": "ORDER_NOT_FOUND"
}
~~~

Trong module **INTEGRATION_API_REST**, bài học kết hợp resource/HTTP, OpenAPI, phân quyền và idempotency với WebFlux/Reactor. Cần xác minh behavior trên bản Spring cụ thể.

**Mục tiêu:** phân biệt empty/error signal, map lỗi theo tầng, dùng RFC 9457 an toàn, xử lý retry/timeout và kiểm thử với WebTestClient.

> **Nguyên tắc:** Reactive thay đổi cách **lỗi được truyền qua pipeline**, không thay đổi ý nghĩa của 400, 401, 403, 404, 409, 412, 429 hay 5xx. Lỗi đã xảy ra phải được chuyển thành HTTP response **trước khi response được commit**, nếu muốn gửi một Problem Details JSON đầy đủ.

## 2. Tư duy Reactor: giá trị, rỗng và lỗi là ba trường hợp khác nhau

Một Mono phát tối đa một phần tử rồi hoàn thành, hoặc hoàn thành rỗng, hoặc kết thúc bằng tín hiệu lỗi. Flux có thể phát nhiều phần tử trước khi hoàn thành hoặc lỗi. Theo Reactive Streams, **error là terminal signal**.

~~~text
Mono.just(order)        -> onNext(order), onComplete
Mono.empty()            -> onComplete (không có giá trị)
Mono.error(exception)   -> onError(exception)

Flux: onNext(A), onNext(B), onError(failure)
      (không có onComplete sau onError)
~~~

| Cơ chế | Khi nào dùng? | Sai lầm thường gặp |
|---|---|---|
| **switchIfEmpty** | Không có giá trị/tài nguyên trong Mono | Coi mọi Mono.empty là lỗi máy chủ |
| **onErrorMap** | Đổi một lỗi kỹ thuật thành lỗi domain đã định nghĩa | Gộp tất cả Throwable thành cùng lỗi 400 |
| **onErrorResume** | Phục hồi có chủ đích bằng publisher khác | Nuốt lỗi DB rồi trả dữ liệu rỗng như thành công |
| **doOnError** | Quan sát/log/metric, không thay đổi tín hiệu | Tưởng rằng log là xử lý lỗi |
| **retryWhen** | Lặp đăng ký subscription khi điều kiện retry an toàn | Retry POST thanh toán và tạo side effect trùng |

### 2.1. Tài nguyên không tồn tại khác lỗi database

~~~java
Mono<OrderView> findOrder(String id, String tenantId) {
    return repository.findVisibleByIdAndTenant(id, tenantId)
        .map(mapper::toView)
        .switchIfEmpty(Mono.error(new OrderNotFoundException()));
}
~~~

Hợp đồng của repository ở đây: **Mono.empty()** nghĩa là không có order *được phép đọc*, còn lỗi kết nối/database đi vào **onError**. Cách xử lý trên giữ lỗi hạ tầng nguyên vẹn để tầng xử lý chung phân loại thành 5xx thay vì trả 404 sai.

**Không làm:**

~~~java
return repository.findVisibleByIdAndTenant(id, tenantId)
    .onErrorResume(error -> Mono.empty()); // Che giấu outage thành 404
~~~

Với lỗi database, một empty fallback có thể khiến client hiểu nhầm “đơn bị xóa”. Đối với dữ liệu tài chính/đơn hàng, lựa chọn fallback phải dựa trên một chính sách nhất quán và nguồn dữ liệu đáng tin, không phải cách tránh stack trace.

### 2.2. Lỗi phát sinh khi subscribe

Phần lớn xử lý reactive chạy **khi subscribe**. try/catch quanh lệnh trả Mono không bắt được error signal phát sau đó từ DB/WebClient. Hãy dùng operator hoặc để WebFlux xử lý. Nếu code đồng bộ có thể throw khi tạo publisher, dùng:

~~~java
return Mono.defer(() -> buildOperation(id))
    .onErrorMap(KnownInfrastructureException.class,
        ex -> new DownstreamUnavailableException(ex));
~~~

Không gọi **subscribe() thủ công** rồi trả 200 khi lệnh chưa xong. Việc xử lý nền cần **202 + operation resource** với intent bền vững.

## 3. Phân loại lỗi theo HTTP và quyền truy cập

| Tình huống xác định | Status thường dùng | Lưu ý |
|---|---|---|
| JSON sai cú pháp hoặc không bind được DTO | **400 Bad Request** | Không phải 500 |
| DTO không đạt ràng buộc đầu vào | **400** theo mặc định thường gặp; hoặc **422** nếu contract chọn | Đồng bộ advice, OpenAPI và tests |
| Thiếu token/token không hợp lệ | **401 Unauthorized** | Có challenge WWW-Authenticate phù hợp |
| Đã xác thực nhưng thiếu quyền | **403 Forbidden** | Có thể chọn 404 để che giấu tài nguyên theo policy |
| ID không tồn tại/không được phép thấy | **404 Not Found** | Không suy từ lỗi DB thành 404 |
| Trạng thái nghiệp vụ mâu thuẫn | **409 Conflict** | Ví dụ đơn đã hủy, key lũy đẳng bị dùng sai |
| If-Match không khớp khi cập nhật | **412 Precondition Failed** | Không ghi đè dữ liệu mới |
| Quá số lần gọi | **429 Too Many Requests** | Retry-After nếu có chính sách retry |
| Dependency tạm không phục vụ được | **503 Service Unavailable** | Có thể thêm Retry-After |
| Gateway hết thời gian chờ upstream | **504 Gateway Timeout** | Không có nghĩa upstream rollback |
| Bug nội bộ hoặc lỗi không phân loại | **500 Internal Server Error** | Không trả stack trace cho client |

**Timeout là kết quả quan sát qua mạng, không phải chắc chắn thất bại nghiệp vụ**. Khi POST có side effect, retry chỉ an toàn với hợp đồng lũy đẳng/operation status phù hợp. Spring/WebClient không tự biết một payment provider đã thu tiền trước khi timeout.

### 3.1. Lỗi cần được phát hiện ở đúng tầng

**Codecs/binding** xử lý JSON/media/size; **Spring Security** xử lý 401/403; **DTO** kiểm cấu trúc; **service/domain** kiểm tenant/state; **repository/WebClient** báo dependency failures; **response writer** xử lý serialization/disconnect. Không map mọi exception thành 400 hoặc đưa thông báo nội bộ vào response.

## 4. RFC 9457 Problem Details trong WebFlux

**Problem Details** quy định một cấu trúc mô tả lỗi bằng **application/problem+json**:

**type** là URI nhận diện loại lỗi (mặc định about:blank khi vắng); **title** là tiêu đề; **status** là mã HTTP; **detail** mô tả lần lỗi; **instance** là URI tham chiếu lần xảy ra. **code, invalidParams, correlationId** là extension của ứng dụng, không phải thành viên chuẩn bắt buộc.

Trong Spring Framework hiện đại có **org.springframework.http.ProblemDetail**. Các extension được thêm qua setProperty và serializer có thể hiển thị như thành viên JSON ở cấp cao nhất.

Không trả exception message có SQL, token, PII hoặc stack trace; dùng **code** ổn định cho client thay vì parse chuỗi detail.

### 4.1. Một response validation có lỗi theo trường

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "Dữ liệu yêu cầu không hợp lệ",
  "code": "VALIDATION_FAILED",
  "invalidParams": [
    {"name":"items[0].quantity","reason":"must be greater than 0"}
  ]
}
~~~

**invalidParams** là extension cần định nghĩa. Giới hạn số lỗi/độ dài reason; có thể dịch title/detail nhưng giữ code/field path ổn định.

## 5. Annotated controller: lỗi từ Mono đi vào @RestControllerAdvice

### 5.1. DTO và service reactive

Giả định OrdersService dùng **repository/driver không chặn luồng** như R2DBC và đã có cơ chế kiểm tra tenant, trạng thái đơn, idempotency. Không gọi JPA/JDBC blocking trực tiếp trên event-loop của WebFlux.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import reactor.core.publisher.Mono;

record ItemInput(
        @NotBlank String sku,
        @Min(1) int quantity) {}

record CreateOrderRequest(
        @NotBlank String customerId,
        @NotEmpty List<@Valid ItemInput> items) {}

record OrderView(String id, String status, long totalAmount) {}

interface OrdersService {
    // Mono.empty() khi không có order mà caller được phép xem;
    // lỗi hạ tầng phải đi qua onError.
    Mono<OrderView> findVisible(
            String orderId, String tenantId, String subject);

    // Phải bảo đảm cùng idempotency key/payload không tạo hai orders.
    Mono<OrderView> create(
            CreateOrderRequest input, String key,
            String tenantId, String subject);
}

class OrderNotFoundException extends RuntimeException {}
class OrderConflictException extends RuntimeException {}
~~~

### 5.2. GET và POST theo contract

~~~java
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
class OrdersController {
    private final OrdersService orders;

    OrdersController(OrdersService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderView>> get(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {

        String tenant = requireTenant(jwt);
        return orders.findVisible(id, tenant, jwt.getSubject())
            .switchIfEmpty(Mono.error(new OrderNotFoundException()))
            .map(view -> ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(view));
    }

    @PostMapping(consumes = "application/json")
    Mono<ResponseEntity<OrderView>> create(
            @Valid @RequestBody Mono<CreateOrderRequest> body,
            @RequestHeader("Idempotency-Key") String key,
            @AuthenticationPrincipal Jwt jwt) {

        String tenant = requireTenant(jwt);
        return body.flatMap(dto ->
                orders.create(dto, key, tenant, jwt.getSubject()))
            .map(view -> ResponseEntity
                .created(URI.create("/api/orders/" + view.id()))
                .cacheControl(CacheControl.noStore())
                .body(view));
    }

    private String requireTenant(Jwt jwt) {
        if (jwt == null) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.UNAUTHORIZED);
        }
        String tenant = jwt.getClaimAsString("tenant_id");
        if (tenant == null || tenant.isBlank()) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.FORBIDDEN);
        }
        return tenant;
    }
}
~~~

Đây là **fragment** cần JWT/security, repository, error mapping và tests. Với **@Valid @RequestBody Mono<CreateOrderRequest>**, validation có thể phát lỗi sau khi body giải mã trong publisher. Test WebFlux thực; tham số DTO trực tiếp cũng được hỗ trợ nhưng thời điểm xử lý có thể khác.

Không gọi **block()/get()** hoặc JDBC blocking trên event-loop. Với legacy driver, dùng thread-scheduling có giới hạn và đánh giá Spring MVC thay thế.

### 5.3. Advice cho domain error

~~~java
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class OrderProblemAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> missing() {
        ProblemDetail p = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        p.setType(URI.create(
            "https://api.example.test/problems/order-not-found"));
        p.setTitle("Order not found");
        p.setProperty("code", "ORDER_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .cacheControl(CacheControl.noStore())
            .body(p);
    }
}
~~~

Ánh xạ **OrderConflictException → 409** tương tự với type/code riêng. WebFlux tìm @ExceptionHandler phù hợp cho error signal của annotated controller khi chưa commit. **Không bắt mọi Throwable** ở advice rồi trả lỗi 400; giữ lỗi hạ tầng ở 5xx và log an toàn.

### 5.4. Advice cho Bean Validation

Với input object bị @Valid từ chối, WebFlux thường đưa ra **WebExchangeBindException**. Có thể bổ sung vào advice:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.support.WebExchangeBindException;

@ExceptionHandler(WebExchangeBindException.class)
ResponseEntity<ProblemDetail> invalid(WebExchangeBindException ex) {
    List<Map<String, String>> invalidParams =
        ex.getFieldErrors().stream()
            .limit(20)
            .map(error -> Map.of(
                "name", error.getField(),
                "reason", Objects.toString(
                    error.getDefaultMessage(), "Invalid value")))
            .toList();

    ProblemDetail p = ProblemDetail.forStatus(
        HttpStatus.BAD_REQUEST);
    p.setType(URI.create(
        "https://api.example.test/problems/invalid-request"));
    p.setTitle("Invalid request");
    p.setProperty("code", "VALIDATION_FAILED");
    p.setProperty("invalidParams", invalidParams);
    return ResponseEntity.badRequest()
        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
        .body(p);
}
~~~

Đây là **method fragment cần đặt trong @RestControllerAdvice**, không phải method top-level Java. Cần xử lý thêm object/global errors và response kích thước giới hạn. **Lỗi JSON parse/binding** như sai enum hoặc sai kiểu có thể đi qua **ServerWebInputException** và handler khác, không mặc định mọi lỗi đầu vào đều là WebExchangeBindException.

Trong các bản Spring Framework hỗ trợ **method validation**, constraint đặt trực tiếp lên parameter hoặc return value có thể đi qua **HandlerMethodValidationException**. Cần phân biệt lỗi **tham số của client** với lỗi **giá trị trả về từ server**; không biến bug server thành 400. Chữ ký advice/handler và API để lấy validation results có thể khác giữa dòng framework, nên hãy kiểm thử trên phiên bản project đang dùng.

## 6. Annotated controller, functional endpoint và global handler

WebFlux có hai phong cách server phổ biến:

- **Annotated controllers**: @RestController, @GetMapping, @RestControllerAdvice; phù hợp ứng dụng theo controller/DTO truyền thống.
- **Functional endpoints**: RouterFunction/HandlerFunction với **ServerRequest → Mono<ServerResponse>**; xử lý lỗi theo pipeline, filter của router hoặc error handler ở tầng WebFlux.

### 6.1. Functional endpoint trả Problem Details

~~~java
// Fragment trong @Configuration, dùng static imports route() và GET():
@Bean
RouterFunction<ServerResponse> routes(OrdersHandler handler) {
    return route(GET("/api/orders/{id}"), handler::get);
}

// Fragment trong OrdersHandler, đã có OrdersService và caller context:
Mono<ServerResponse> get(ServerRequest req) {
    return caller.authorized(req)
        .flatMap(c -> orders.findVisible(
            req.pathVariable("id"), c.tenant(), c.subject()))
        .flatMap(view -> ServerResponse.ok().bodyValue(view))
        .switchIfEmpty(Mono.defer(() ->
            ServerResponse.status(404)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .bodyValue(notFoundProblem())));
}
~~~

Đây là các **fragment**: cần OrdersHandler, caller.authorized, notFoundProblem trả ProblemDetail và imports phù hợp. **Không triển khai cùng đường dẫn với annotated controller** vì sẽ trùng route. caller.authorized phải dùng security context đáng tin và phát 401/403 đúng; nếu nó trả Mono.empty khi token sai, switchIfEmpty có thể nhầm thành 404.

Với nhiều routes, tái sử dụng hàm tạo Problem Details. **@RestControllerAdvice không bao phủ mọi functional handler, WebFilter và codec failure**.

### 6.2. Global WebFlux error handling

WebFlux có **WebExceptionHandler / ErrorWebExceptionHandler** và Spring Boot có error handling mặc định. Khi tùy biến global handler, phải xét response đã commit, content negotiation, message writers và thứ tự filter; test lỗi binding, security, domain và streaming.

| Lớp | Phạm vi phù hợp |
|---|---|
| **onErrorResume trong service/handler** | Phục hồi có chủ đích hoặc dịch lỗi cụ thể |
| **@RestControllerAdvice** | Domain/binding errors của annotated controllers |
| **Functional handler/filter** | Lỗi do functional route và pipeline của nó phát sinh |
| **Spring Security WebFilter/entry point** | 401/403 khi xác thực/phân quyền |
| **Global WebFlux error handler** | Lỗi ngoài các handler được định nghĩa; 5xx fallback |

Tránh global handlers cạnh tranh thứ tự; dùng **error taxonomy/JSON schema chung** cho các tầng.

## 7. Spring Security trong reactive stack: đừng làm mất 401/403

WebFlux sử dụng **SecurityWebFilterChain** và **ServerHttpSecurity** chứ không phải Servlet SecurityFilterChain/HttpSecurity của Spring MVC:

~~~java
// Fragment @Bean, dùng ServerHttpSecurity và SecurityWebFilterChain.
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        // Chỉ phù hợp với API stateless bearer, không dùng cookie login.
        .csrf(csrf -> csrf.disable())
        .authorizeExchange(ex -> ex
            .pathMatchers("/actuator/health").permitAll()
            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .pathMatchers(HttpMethod.POST, "/api/orders")
                .hasAuthority("SCOPE_orders.write")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> {}))
        .build();
}
~~~

Phải cấu hình **ReactiveJwtDecoder** xác minh issuer, signature, expiration, audience; scope mapping theo contract. **ServerAuthenticationEntryPoint** xử lý 401, **ServerAccessDeniedHandler** xử lý 403; advice controller không thay các handler này.

Khi tùy biến hai handler bảo mật để dùng Problem Details, phải giữ **WWW-Authenticate** challenge hợp lệ cho bearer token và mã 401/403 thích hợp. Exception chỉ phát sinh trong WebFilter chain có thể không đi qua @RestControllerAdvice của controller. Lỗi auth phải được kiểm thử ở tầng HTTP, không chỉ bằng một unit test service.

**Phân quyền mức tài nguyên:** Đã qua SCOPE_orders.read vẫn chưa đủ để đọc mọi đơn. Service/repository phải giới hạn theo tenant/owner từ principal **đã xác minh**. Nếu chính sách cố ý trả 404 cho resource ngoài quyền, cần duy trì cách che giấu nhất quán; không rò rỉ thông tin qua error detail, thời gian phản hồi hoặc cache chung.

## 8. WebClient: phân biệt downstream HTTP error, network error và timeout

Một reactive service thường gọi API khác bằng **WebClient**. Mặc định, WebClient.retrieve() chuyển HTTP 4xx/5xx thành WebClientResponseException khi truy xuất body; lỗi kết nối, TLS hoặc timeout có thể là các exception khác. Không nên coi toàn bộ lỗi downstream là “resource không tồn tại” của API của bạn.

~~~java
// Fragment dùng WebClient, HttpStatusCode và Mono đã import.
record InventoryView(String sku, boolean available) {}
class InventoryUnavailableException extends RuntimeException {
    InventoryUnavailableException(String message) { super(message); }
}

Mono<InventoryView> findInventory(WebClient client, String sku) {
    return client.get()
        .uri("/internal/inventory/{sku}", sku)
        .retrieve()
        .onStatus(HttpStatusCode::is5xxServerError, response ->
            response.releaseBody().then(Mono.error(
                new InventoryUnavailableException(
                    "Inventory service unavailable"))))
        .bodyToMono(InventoryView.class);
}
~~~

Fragment chỉ ánh xạ **5xx từ inventory service**. Với 4xx/network timeout/lỗi giải mã cần chính sách riêng; cấu hình baseUrl, service authentication, timeouts, pool, giới hạn response và tracing. **Không lộ token/PII/upstream details**.

### 8.1. Timeout và retry có điều kiện

~~~java
// Fragment dùng Duration, Retry và findInventory(client, sku).
Mono<InventoryView> safeRead =
    findInventory(client, "BOOK-01")
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
            .filter(error -> error instanceof InventoryUnavailableException))
        .onErrorMap(InventoryUnavailableException.class,
            error -> new ServiceUnavailableException(error));
~~~

Đây là **fragment minh họa**, chỉ retry lỗi được phân loại. ServiceUnavailableException là exception ứng dụng cần ánh xạ thành 503. Reactor timeout có thể tạo TimeoutException riêng; ví dụ trên **không retry TimeoutException**, cũng không mặc định mọi timeout đều nên retry. Hãy xét SLA, tổng deadline và **retry budget của cả chuỗi**, tránh mỗi tầng đều retry làm bão request.

Với **POST thanh toán hoặc tạo lệnh**, timeout có thể xảy ra **sau khi downstream đã commit**: không tự retry với idempotency key mới. Cần key bền vững, operation status và đối soát; việc gọi reactive không mang lại bảo đảm exactly-once.

### 8.2. Chỉ dịch lỗi mà bạn thực sự hiểu

Downstream 404 không nhất thiết nghĩa là order API phải trả 404: SKU không có có thể là dữ liệu nhập sai hoặc catalog chưa đồng bộ. Dịch lỗi tại tầng integration theo **ngữ nghĩa domain**, không lộ upstream hostname, Authorization hay stack trace.

## 9. Response đã commit, streaming và lỗi sau khi gửi dữ liệu

Trước khi phát response header/body, WebFlux có thể đổi lỗi thành Problem Details. Nhưng với Flux stream dài, server có thể đã gửi một phần:

~~~text
GET /api/events
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: order-update
data: {"id":"ord-42","status":"CONFIRMED"}

... upstream phát onError khi stream đã gửi dữ liệu ...
~~~

**Không thể đổi status 200 đã gửi thành 500 rồi thay toàn bộ body bằng application/problem+json.** Khi response đã commit, lỗi thường dẫn tới kết thúc stream/connection hoặc cơ chế thông báo lỗi **trong giao thức stream** nếu đã định nghĩa từ đầu.

Với **Server-Sent Events**, có thể thiết kế event lỗi mang code máy đọc được và chính sách reconnect, nhưng **không gửi stack trace và không coi nó là một response HTTP Problem Details mới**. Client cần biết event lỗi và lỗi kết nối có ý nghĩa gì; tránh tự phát retry vô hạn cho stream mất quyền hoặc operation đã kết thúc.

Với download lớn, lỗi stream có thể khiến file thiếu bytes dù status đầu là 200; cần size/checksum và chỉ hỗ trợ HTTP Range khi storage/proxy thực sự đáp ứng.

### 9.1. Không giải quyết lỗi reactive bằng block()

Tránh **block() trên event-loop**, **subscribe() thủ công**, nuốt mọi lỗi bằng onErrorResume(...Mono.empty()), onErrorContinue thiếu kiểm soát, và retry vô hạn với POST có side effect. doOnError chỉ quan sát, không phải phục hồi. Mỗi retry phải định nghĩa **lỗi nào an toàn, ngân sách thời gian/số lần và cách theo dõi thất bại**.

## 10. WebTestClient và StepVerifier: kiểm cả HTTP lẫn error signal

**WebTestClient** giúp gửi request theo mô hình WebFlux và xác minh status/header/body. Với unit test của service reactive, dùng **StepVerifier** để kiểm tra publisher hoàn thành, rỗng hay lỗi.

### 10.1. HTTP contract tests

Fragment trong một test đã cấu hình WebTestClient, mock OrdersService, Spring Security Test:

~~~java
client.mutateWith(mockJwt()
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get().uri("/api/orders/ord-missing")
    .exchange()
    .expectStatus().isNotFound()
    .expectHeader().contentTypeCompatibleWith(
        MediaType.APPLICATION_PROBLEM_JSON)
    .expectBody()
    .jsonPath("$.status").isEqualTo(404)
    .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND");
~~~

Các API mockJwt(), SimpleGrantedAuthority, MediaType và client cần imports/fixture phù hợp. **mockJwt()** gắn authentication giả lập để test filter/authority; nó **không chứng minh token chữ ký sai, issuer/audience sai hoặc token hết hạn bị decoder thật từ chối**. Cần thêm integration tests cho ReactiveJwtDecoder và kiểm tra tenant từ verified claims.

### 10.2. Test reactive service bằng StepVerifier

~~~java
StepVerifier.create(orderService.findVisible(
        "ord-missing", "tenant-A", "user-17"))
    .expectError(OrderNotFoundException.class)
    .verify();
~~~

Nếu service contract trả Mono.empty() khi không tìm thấy, StepVerifier phải dùng **verifyComplete()** và việc chuyển empty → 404 được test ở controller; đừng đổi ngữ nghĩa service chỉ để test dễ. Với timeout/backoff, dùng **virtual time** nếu phù hợp, tránh Thread.sleep dài hoặc flaky test.

### 10.3. Ma trận lỗi nên tự động hóa

| Thử nghiệm | Kỳ vọng |
|---|---|
| JSON sai cú pháp hoặc quantity = 0 | 400, response lỗi đúng schema |
| Thiếu/hỏng bearer token | 401 với challenge phù hợp |
| Scope không đủ hoặc resource tenant khác | 403/404 theo policy; không lộ dữ liệu |
| Mono.empty() từ truy vấn visible order | 404; không biến thành 200 null |
| DB down hoặc exception không phân loại | 5xx với detail an toàn, có log/trace |
| Business state conflict, If-Match mismatch | 409, 412 đúng contract |
| Downstream 503/timeout | Mapping/retry có giới hạn, không trả 404 giả |
| Client disconnect khi SSE đang chạy | Stream kết thúc/cleanup tài nguyên, không cố ghi Problem JSON |
| POST timeout sau commit | Retry cùng key không tạo order trùng |

Trong test cấu hình nhiều tầng, phải kiểm tra lỗi **trước và sau response commit**; không chỉ assert body với happy path. Test WebFilter/Security riêng vì @RestControllerAdvice có thể không xử lý các lỗi đó.

## 11. OpenAPI và quan sát vận hành

Mô tả rõ response lỗi trong OpenAPI, không chỉ dùng @ExceptionHandler trong code:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      responses:
        '200':
          description: Order representation
        '400':
          description: Invalid request
        '401':
          description: Authentication required
        '403':
          description: Forbidden
        '404':
          description: Order absent or hidden
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/ApiProblem'
components:
  schemas:
    ApiProblem:
      type: object
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        code: {type: string}
~~~

Đây là **fragment**, không phải toàn bộ OpenAPI; cần mô tả securitySchemes, path parameter id, schema 200 và các lỗi khác. **Một tài liệu OAS hợp lệ không tự thực thi handler**, và OAS generator có thể bỏ sót lỗi từ WebFilter, gateway hoặc reactive dependency.

Quan sát vận hành nên đo **tỷ lệ 4xx/5xx theo route/code**, timeout downstream, retry count, p95/p99, memory/buffer limits và số stream bị ngắt. Gắn correlation/trace ID an toàn, không dùng raw token, customer ID hoặc order ID làm metric label cardinality cao; log nội bộ có kiểm soát truy cập. Error response công khai không nên chứa hostname database hay upstream.

## 12. Bài tập và đáp án gợi ý

**Bài 1 — Empty hay error?** Repository trả Mono.empty() vì đơn không tồn tại; thiết kế dùng onErrorResume(e -> Mono.empty()) cho mọi lỗi database. **Đáp án:** Sai vì outage bị che thành 404; switchIfEmpty cho trường hợp không có tài nguyên, giữ DB error để trả 5xx.

**Bài 2 — Chọn tầng xử lý.** Token JWT sai chữ ký, OrderNotFoundException từ controller và lỗi trong functional route. **Đáp án:** Token do SecurityWebFilterChain/entry point xử lý; domain exception của annotated controller do advice; functional route xử lý trong handler/filter/global error handler phù hợp.

**Bài 3 — 200 đã gửi.** Flux đã phát 10 SSE events rồi gặp timeout từ downstream. Có thể đổi response thành HTTP 503 application/problem+json? **Đáp án:** Không, status/header đã commit; đóng stream hoặc phát error event theo giao thức đã định nghĩa, hỗ trợ reconnect có kiểm soát.

**Bài 4 — Retry POST.** Payment provider đã xử lý charge nhưng WebClient timeout; lập trình viên thêm retryWhen cho mọi exception. **Đáp án:** Nguy cơ thu tiền hai lần. Giữ idempotency key, tra cứu operation/provider và chỉ retry khi hợp đồng chứng minh an toàn.

**Bài 5 — Bảo mật.** GET /orders/42 có scope orders.read nhưng trả đơn của tenant khác. **Đáp án:** Cần resource-level authorization trong service/query và negative integration test; scope không cấp quyền cho mọi tài nguyên.

## 13. Checklist và kết luận

- [ ] Phân biệt Mono.empty(), onError và lỗi đã được phục hồi?
- [ ] Không nuốt exception hạ tầng rồi trả 404/200/204 giả?
- [ ] Mỗi mã HTTP phản ánh đúng validation, auth, domain và dependency failure?
- [ ] ProblemDetail có type/title/status/code an toàn, không lộ PII/stack trace?
- [ ] @RestControllerAdvice, functional/global handler và security filter có phạm vi rõ?
- [ ] Request validation, 401/403 và tenant authorization đã được kiểm thử?
- [ ] WebClient có timeout, giới hạn retry và không lặp side effect thiếu idempotency?
- [ ] SSE/file streaming có hành vi sau commit và cleanup rõ?
- [ ] WebTestClient, StepVerifier, OpenAPI và observability đều bao phủ đường lỗi?

**Kết luận:** Trong Spring WebFlux, lỗi là tín hiệu của Mono/Flux và chỉ có thể chuyển thành response HTTP đầy đủ trước khi response commit. Phân loại lỗi ở đúng tầng, trả **Problem Details theo RFC 9457**, giữ nguyên ngữ nghĩa bảo mật và retry, rồi xác minh bằng **WebTestClient/StepVerifier**. Reactive không miễn trừ trách nhiệm về HTTP contract, transaction hay quyền truy cập dữ liệu.

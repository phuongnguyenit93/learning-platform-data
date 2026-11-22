# ServerRequest, ServerResponse và định tuyến hàm

## 1. Vì sao Spring WebFlux có functional endpoints?

Ngoài **@RestController**, Spring WebFlux có **functional endpoints** để tách **khớp tuyến** khỏi **xử lý request**. API vẫn tuân hợp đồng REST bình thường: resource/URI, HTTP method/status, JSON, cache, phân quyền và lỗi.

Bài thuộc chương **Spring WebFlux** của module **INTEGRATION_API_REST**. Trọng tâm là **ServerRequest, ServerResponse và định tuyến hàm**, kết hợp reactive service, validation, bảo mật, OpenAPI và test bằng Java 17+/Spring Framework 6/Boot 3.x.

Mục tiêu: xây **RouterFunction<ServerResponse>** cho GET/POST, dùng **RequestPredicate** chọn route, đọc body/query/header từ **ServerRequest**, trả **Mono<ServerResponse>** với status/Location/Problem Details, tránh chặn event loop và kiểm thử bằng **WebTestClient**.

**Functional routing không tự làm code non-blocking**: JDBC, Thread.sleep hoặc block() trong handler vẫn có thể nghẽn request thread.

## 2. Năm thành phần và reactive pipeline

~~~java
HandlerFunction<ServerResponse> hello =
    request -> ServerResponse.ok().bodyValue("hello");
~~~

| Thành phần | Vai trò |
| --- | --- |
| **ServerRequest** | HTTP method, path, query, headers, principal và đọc body qua **bodyToMono/bodyToFlux**. |
| **ServerResponse** | Tạo status, headers, body bằng **ok/created/noContent/status/bodyValue/body**. |
| **HandlerFunction<ServerResponse>** | Hàm **ServerRequest → Mono<ServerResponse>**. |
| **RouterFunction<ServerResponse>** | Chọn handler bằng các RequestPredicate. |
| **RequestPredicate** | Khớp method/path/header/media type; có thể kết hợp and/or. |

**Mono** biểu diễn 0 hoặc 1 kết quả; **Flux** biểu diễn 0..N kết quả. Reactor Publisher giúp WebFlux điều phối subscription, lỗi, cancellation và backpressure nhưng không tự bảo đảm mọi dependency non-blocking.

~~~mermaid
flowchart LR
    A[HTTP client] --> B[WebFilter / Security]
    B --> C[RouterFunction]
    C --> D[HandlerFunction]
    D --> E[Validation + Reactive service]
    E --> F[Mono ServerResponse]
    F --> A
~~~

Router chỉ tìm handler; service phải quyết định nghiệp vụ và quyền. Nếu route không khớp, WebFlux xử lý theo routing/HTTP semantics, **không có nghĩa handler được gọi với body rỗng**.

## 3. Hợp đồng HTTP mẫu: resource đơn hàng

Các URI:

- **GET /api/v1/orders/{id}**: lấy một đơn trong phạm vi caller có quyền.
- **POST /api/v1/orders**: tạo đơn, trả 201 và **Location**.
- **GET /api/v1/orders?status=PENDING&limit=20**: danh sách có giới hạn (bài mở rộng).

Request tạo:

~~~http
POST /api/v1/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json

{
  "productId": "prod-42",
  "quantity": 2
}
~~~

Response thành công:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/ord-501
Content-Type: application/json
Cache-Control: no-store

{
  "id": "ord-501",
  "productId": "prod-42",
  "quantity": 2,
  "status": "PENDING"
}
~~~

GET:

~~~http
GET /api/v1/orders/ord-501 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "ord-501",
  "productId": "prod-42",
  "quantity": 2,
  "status": "PENDING"
}
~~~

Không tìm thấy (hoặc không được phép biết resource có tồn tại, theo chính sách API):

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Không tìm thấy đơn hàng.",
  "code": "ORDER_NOT_FOUND"
}
~~~

**HTTP status, Location, media type và JSON schema** vẫn là hợp đồng REST thông thường. Chọn functional endpoints không thay đổi ý nghĩa các mã HTTP hay quyền truy cập.

## 4. DTO, repository và service: tách khỏi routing

Dùng record cho contract JSON và Bean Validation:

~~~java
public record CreateOrderRequest(
    @NotBlank String productId,
    @NotNull @Min(1) Integer quantity
) {}

public record OrderView(
    String id,
    String productId,
    int quantity,
    String status
) {}
~~~

Một service reactive được mô tả như sau:

~~~java
public interface OrderService {
    Mono<OrderView> findVisible(String tenantId, String orderId);

    Mono<OrderView> create(
        String tenantId, CreateOrderRequest request);

    Flux<OrderView> listVisible(
        String tenantId, String status, int limit);
}
~~~

- **findVisible** trả **Mono.empty()** nếu ID không tồn tại hoặc bị che theo chính sách; handler chọn 404.
- **create** trả một OrderView sau khi nghiệp vụ tạo thành công; có thể phát lỗi nghiệp vụ như **OrderReferenceConflict**.
- **listVisible** trả stream các item thuộc tenant, với thứ tự và giới hạn được xác định.

Đây là **interface do ứng dụng định nghĩa**, không phải một interface Spring Data có sẵn. Implementation có thể dùng **Spring Data R2DBC** hoặc một reactive client phù hợp; không nên gọi **JpaRepository** đồng bộ trực tiếp trong event loop và cho rằng return **Mono.just(...)** đã biến lời gọi thành non-blocking.

**Tenant ID phải được suy ra từ principal/token đã xác thực**, không lấy từ query parameter **tenantId** do client tự gửi. Service kiểm tra quyền truy cập cả khi truy vấn chi tiết lẫn khi tính số lượng/phân trang.

## 5. RouterFunction: đăng ký tuyến rõ ràng

Cấu hình định tuyến hàm bằng **@Bean**:

~~~java
@Configuration
public class OrderRoutes {

    @Bean
    RouterFunction<ServerResponse> orders(OrderHandler handler) {
        return RouterFunctions.route()
            .GET("/api/v1/orders", handler::list)
            .GET("/api/v1/orders/{id}", handler::get)
            .POST("/api/v1/orders", handler::create)
            .build();
    }
}
~~~

Handler sẽ được Spring inject dependency từ container. Trong dự án thật, phải import **RouterFunction**, **RouterFunctions**, **ServerResponse** và bean handler. **RouterFunction** ở đây là một bean thuộc WebFlux functional endpoints; không trộn nhầm với **RouterFunction** của Spring MVC.fn (có tên lớp tương tự ở package khác).

### Predicate khác route handler

Có thể định tuyến theo điều kiện:

~~~java
RouterFunction<ServerResponse> jsonGet =
    RouterFunctions.route(
        RequestPredicates.GET("/api/v1/orders/{id}")
            .and(RequestPredicates.accept(MediaType.APPLICATION_JSON)),
        handler::get);
~~~

Đây là route chỉ khớp request có Accept phù hợp. Nhưng **một predicate không khớp thường dẫn tới việc tìm route khác/404**, chứ không tự tạo chính xác **406 Not Acceptable**. Tương tự, thêm **contentType(application/json)** vào route POST mà request gửi text/plain có thể tạo **404** thay vì **415 Unsupported Media Type**.

**Nguyên tắc khi xây public API:** nếu contract yêu cầu 406/415, đừng chỉ dựa vào route predicates để suy status. Có thể route theo **method + path**, sau đó kiểm tra Content-Type/Accept trong handler hoặc dùng một strategy xử lý lỗi media type nhất quán. Viết test cho cả hai trường hợp.

### Nhiều tuyến, thứ tự và grouping

- Phân biệt **GET /orders/search** với **GET /orders/{id}**; đăng ký tuyến tĩnh/specific trước route tham số để tránh **search** bị hiểu là ID.
- Có thể dùng **andRoute(...)**, **nest(path("/api/v1"), ...)** hoặc API **RouterFunctions.route().path(..., builder -> ...)** để nhóm route chung; đừng tạo nhiều prefix thủ công dễ lệch.
- **GET**, **HEAD** và **OPTIONS** có semantics HTTP riêng; không tự giả rằng đăng ký GET bao phủ toàn bộ contract HEAD/OPTIONS trong mọi cấu hình. Kiểm thử khi API dựa vào các phương thức đó.
- Nếu cần versioned URI, công bố rõ **/api/v1/...**. Version từ URL không phải phép thay thế cho OpenAPI và khả năng tương thích.

RouterFunction và annotated controllers có thể cùng tồn tại trong một ứng dụng nhưng phải tránh route trùng/ưu tiên handler không chủ ý.

## 6. ServerRequest: đọc dữ liệu HTTP theo hợp đồng

**ServerRequest** cung cấp các thao tác:

~~~java
String id = request.pathVariable("id");
String status = request.queryParam("status").orElse("PENDING");

List<MediaType> accepts = request.headers().accept();
Optional<MediaType> contentType = request.headers().contentType();

Mono<CreateOrderRequest> input =
    request.bodyToMono(CreateOrderRequest.class);

Mono<? extends Principal> principal =
    request.principal();
~~~

**Path variable** và query string đều là input không đáng tin: validate độ dài, định dạng ID, giới hạn **limit**, danh sách sort được phép và scope tenant; không nối trực tiếp vào SQL.

**bodyToMono(CreateOrderRequest.class)** là cách đọc một JSON object; request body sẽ được decode khi reactive chain được subscribe. Với upload/streaming có thể dùng **bodyToFlux(...)**, multipart APIs hoặc DataBuffer đúng chính sách; đừng đọc cả file lớn vào bộ nhớ chỉ để tiện xử lý.

Khác với controller annotation, **@Valid trên parameter của một HandlerFunction không tự động kích hoạt như @Valid @RequestBody**. Functional handler cần gọi **jakarta.validation.Validator** hoặc một validation component phù hợp sau khi deserialize.

### Kiểm tra body rỗng

Với **POST /orders** yêu cầu JSON object, **Mono.empty()** từ bodyToMono (body không có dữ liệu) phải trở thành một lỗi như **400**, không âm thầm tạo một đơn trống:

~~~java
request.bodyToMono(CreateOrderRequest.class)
    .switchIfEmpty(Mono.error(
        new InvalidOrder("Request body is required")));
~~~

Với PUT/PATCH, cần phân biệt body thiếu, JSON null và field vắng mặt theo contract. Không suy rằng bodyToMono tự chuyển mọi schema violation thành cùng một domain exception.

## 7. ServerResponse: status, headers và body

Các builder hay dùng:

~~~java
// JSON cho một resource.
Mono<ServerResponse> ok =
    ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(orderView);

// Tạo resource: URI-reference đến tài nguyên mới.
Mono<ServerResponse> created =
    ServerResponse.created(URI.create("/api/v1/orders/ord-501"))
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(orderView);

// Xóa thành công, không có body.
Mono<ServerResponse> deleted =
    ServerResponse.noContent().build();

// Response không có body khi đã biết mã.
Mono<ServerResponse> accepted =
    ServerResponse.accepted().build();
~~~

**bodyValue(...)** dùng cho một giá trị thường (POJO/DTO). Không truyền **Mono** hoặc **Flux** vào bodyValue để nhét Publisher như một object; dùng **body(publisher, ElementClass.class)** hoặc **BodyInserters.fromPublisher** để framework subscribe/encode đúng:

~~~java
Flux<OrderView> rows = service.listVisible(tenant, "PENDING", 20);

Mono<ServerResponse> response =
    ServerResponse.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(rows, OrderView.class);
~~~

**application/x-ndjson** hoặc **application/ndjson** tùy codec/hợp đồng hỗ trợ thực tế; ví dụ dùng hằng **MediaType.APPLICATION_NDJSON** khi project có hỗ trợ. Với client mong một **JSON array**, không thể đơn giản đổi media type mà giữ semantics. Khi stream JSON/NDJSON, cần mô tả rõ trạng thái, thứ tự, cách kết thúc và cách xử lý nếu producer lỗi sau khi headers đã được gửi.

**ServerResponse.created(...)** tạo status 201 + Location; body không bắt buộc bởi HTTP nhưng API này cam kết có body. **ServerResponse.noContent()** trả 204 và không có representation body.

## 8. HandlerFunction: GET và POST với Mono<ServerResponse>

Giả sử **TenantAccess** đọc tenant đã được xác thực từ **Authentication** và kiểm tra quyền. Một handler có thể dùng constructor injection:

~~~java
@Component
public class OrderHandler {
    private final OrderService service;
    private final Validator validator;
    private final TenantAccess tenantAccess;

    public OrderHandler(
            OrderService service,
            Validator validator,
            TenantAccess tenantAccess) {
        this.service = service;
        this.validator = validator;
        this.tenantAccess = tenantAccess;
    }

    private Mono<String> tenant(ServerRequest request) {
        return request.principal()
            .cast(Authentication.class)
            .switchIfEmpty(Mono.error(
                new AuthenticationRequired()))
            .map(tenantAccess::authorizedTenantId);
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        String orderId = request.pathVariable("id");

        return tenant(request)
            .flatMap(tenantId ->
                service.findVisible(tenantId, orderId))
            .switchIfEmpty(Mono.error(new OrderNotFound()))
            .flatMap(order -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .cacheControl(CacheControl.noStore())
                .bodyValue(order));
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return tenant(request)
            .flatMap(tenantId ->
                request.bodyToMono(CreateOrderRequest.class)
                    .switchIfEmpty(Mono.error(
                        new InvalidOrder("Body is required")))
                    .flatMap(dto -> {
                        Set<ConstraintViolation<CreateOrderRequest>>
                            problems = validator.validate(dto);
                        if (!problems.isEmpty()) {
                            return Mono.<OrderView>error(
                                new InvalidOrder("Invalid order fields"));
                        }
                        return service.create(tenantId, dto);
                    }))
            .flatMap(order -> ServerResponse
                .created(URI.create(
                    "/api/v1/orders/" + order.id()))
                .contentType(MediaType.APPLICATION_JSON)
                .cacheControl(CacheControl.noStore())
                .bodyValue(order));
    }
}
~~~

**OrderNotFound**, **InvalidOrder**, **AuthenticationRequired**, **TenantAccess** và **OrderService** là các loại của ứng dụng minh họa; cần định nghĩa cùng error mapping và security. **AuthenticationRequired** trong handler không thay thế cấu hình SecurityWebFilterChain và challenge 401.

**Lưu ý về Publisher:** không gọi **subscribe()** thủ công trong handler. Hãy **return Mono** để WebFlux quản lý subscription, cancellation, context và lỗi. Không dùng **block()** hoặc **blockOptional()** trên request path. Một **Mono.empty()** khi tìm resource không có dữ liệu phải được xử lý trước khi xây 200; ví dụ dùng **switchIfEmpty** thành lỗi 404.

Trong một số thiết kế, validation có thể được tách thành một component nhận DTO và trả **Mono<CreateOrderRequest>** để dùng lại, đồng thời cung cấp danh sách field violations. Ở đây ví dụ tập trung vào pipeline và status HTTP.

## 9. GET collection: validate query và giới hạn Flux

Tuyến **GET /api/v1/orders** ở phần 5 cần phương thức **list** trong OrderHandler. Chỉ cho phép **limit từ 1 đến 100** và status hợp lệ:

~~~java
public Mono<ServerResponse> list(ServerRequest request) {
    return Mono.defer(() -> {
        int limit;
        try {
            limit = Integer.parseInt(
                request.queryParam("limit").orElse("20"));
        } catch (NumberFormatException ex) {
            return Mono.error(new InvalidOrder("Invalid limit"));
        }
        String status = request.queryParam("status")
            .orElse("PENDING");
        if (limit < 1 || limit > 100 ||
                !Set.of("PENDING", "CONFIRMED", "CANCELLED")
                    .contains(status)) {
            return Mono.error(new InvalidOrder("Invalid query"));
        }
        return tenant(request)
            .flatMap(t -> service.listVisible(t, status, limit)
                .collectList())
            .flatMap(rows -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(rows));
    });
}
~~~

**collectList()** giữ các item trong memory; chỉ phù hợp vì có giới hạn 100. Một API phân trang thật còn cần sort ổn định, cursor/offset, next link và quyền theo tenant. Nếu cần truyền stream lớn, dùng **ServerResponse.body(flux, ElementType.class)** với media type như NDJSON/SSE và hợp đồng xử lý luồng lỗi; khi headers đã gửi thì không thể tùy ý đổi sang body lỗi 500.

## 10. Content-Type, Accept và 400/406/415

**RequestPredicate.contentType/accept không tự bảo đảm trả 415/406 khi không khớp**: route có thể chỉ trả 404. Để giữ HTTP contract, route POST theo **path + method** rồi kiểm tra input:

~~~java
if (!request.headers().contentType()
        .map(m -> m.isCompatibleWith(MediaType.APPLICATION_JSON))
        .orElse(false)) {
    return Problems.reply(HttpStatus.UNSUPPORTED_MEDIA_TYPE,
        "unsupported-media-type", "UNSUPPORTED_MEDIA_TYPE",
        "Endpoint chỉ nhận application/json.");
}
// Sau đó bodyToMono + validator + service của phần 8.
~~~

GET/POST chỉ hỗ trợ JSON cần trả **406** nếu **Accept** không cho phép JSON:

~~~http
GET /api/v1/orders/ord-501 HTTP/1.1
Accept: application/xml
~~~

~~~http
HTTP/1.1 406 Not Acceptable
Content-Type: application/problem+json

{"type":"https://api.example.com/problems/not-acceptable",
 "status":406,"code":"NOT_ACCEPTABLE"}
~~~

Khi tự thương lượng định dạng, phải xử lý **wildcard, q-value, q=0, specificity** và media type parameters; không so chuỗi Accept bằng equals/contains. Nếu Content-Type sai trả **415**, JSON sai cú pháp/kiểu thường **400**, còn DTO vi phạm Bean Validation phải được handler **gọi Validator thủ công**. Viết WebTestClient kiểm chứng các nhánh thực, không suy từ route predicate.

## 11. Error handling của functional router

Gắn handler cho các lỗi phát sinh trong routing/handler qua **RouterFunctions.Builder.onError**:

~~~java
@Bean
RouterFunction<ServerResponse> routes(OrderHandler h) {
    return RouterFunctions.route()
        .GET("/api/v1/orders", h::list)
        .GET("/api/v1/orders/{id}", h::get)
        .POST("/api/v1/orders", h::create)
        .onError(InvalidOrder.class,
            (ex, r) -> Problems.reply(HttpStatus.BAD_REQUEST,
                "invalid-order", "INVALID_ORDER", "Invalid input"))
        .onError(OrderNotFound.class,
            (ex, r) -> Problems.reply(HttpStatus.NOT_FOUND,
                "order-not-found", "ORDER_NOT_FOUND", "Order not found"))
        .onError(OrderReferenceConflict.class,
            (ex, r) -> Problems.reply(HttpStatus.CONFLICT,
                "order-conflict", "ORDER_CONFLICT", "Conflict"))
        .onError(ServerWebInputException.class,
            (ex, r) -> Problems.reply(HttpStatus.BAD_REQUEST,
                "invalid-json", "INVALID_JSON", "Invalid JSON"))
        .build();
}
~~~

Helper cho **RFC 9457 Problem Details**:

~~~java
final class Problems {
    static Mono<ServerResponse> reply(
            HttpStatus status, String slug,
            String code, String detail) {
        ProblemDetail pd =
            ProblemDetail.forStatusAndDetail(status, detail);
        pd.setType(URI.create(
            "https://api.example.com/problems/" + slug));
        pd.setProperty("code", code);
        return ServerResponse.status(status)
            .contentType(MediaType.parseMediaType(
                "application/problem+json"))
            .cacheControl(CacheControl.noStore())
            .bodyValue(pd);
    }
}
~~~

**InvalidOrder/OrderNotFound/OrderReferenceConflict** là exception ứng dụng. Không gửi SQL, token, stack trace hoặc thông tin ngoài quyền trong detail. **onError** của router không thay thế cơ chế cho Security WebFilter, lỗi proxy hay route không tồn tại. Riêng **UnsupportedMediaTypeStatusException** và lỗi codec cần kiểm thử để **415 không bị quy thành 400**; với lỗi ngoài router có thể dùng **WebExceptionHandler** phù hợp.

## 12. HandlerFilterFunction và WebFilter

Một functional filter có thể ghi metric quanh handler:

~~~java
RouterFunctions.route()
    .GET("/api/v1/orders", handler::list)
    .filter((req, next) ->
        next.handle(req).doOnError(error ->
            metrics.recordError(req.method().name(), error)))
    .build();
~~~

**HandlerFilterFunction** bao quanh các handler thuộc RouterFunction. **WebFilter** áp dụng ở reactive web filter chain; **SecurityWebFilterChain** chịu trách nhiệm authn/authz/CSRF. Không dùng filter logging để thay thế security hoặc lấy tenant từ header do client tự gửi. Metric nên dùng **route template/status/code**, không dùng raw path có ID cá nhân hoặc requestId làm label high-cardinality. Correlation ID từ client cần được kiểm tra hoặc tạo lại ở hạ tầng tin cậy.

## 13. Non-blocking, backpressure và timeout

Không gọi **block()**, **subscribe()**, **Thread.sleep** hay **JDBC/JPA blocking** ngay trong event loop của WebFlux:

~~~java
// Sai: block trên request thread.
OrderView order = service.findVisible(tenant, id).block();

// Đúng: compose publisher.
return service.findVisible(tenant, id)
    .switchIfEmpty(Mono.error(new OrderNotFound()))
    .flatMap(order -> ServerResponse.ok().bodyValue(order));
~~~

Nếu phải dùng một thư viện blocking khi chuyển đổi hệ thống:

~~~java
Mono<OrderView> result = Mono.fromCallable(
        () -> blockingRepository.findVisible(tenant, id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là **cách cách ly tạm**, không biến JDBC thành non-blocking; cần giới hạn concurrency, timeout và đo pool. Reactive end-to-end phù hợp hơn với R2DBC/reactive HTTP clients. **Flux** không giúp tiết kiệm RAM nếu dùng collectList/buffer không giới hạn: áp limit/page size, codec max-in-memory-size và cancellation. Timeout POST **không chứng minh DB chưa commit**; dùng idempotency hoặc business reference khi retry.

## 14. Bảo mật bằng SecurityWebFilterChain

Ví dụ **Bearer-only stateless API** bảo vệ các functional routes:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers(HttpMethod.GET,
                "/api/v1/orders", "/api/v1/orders/**")
            .hasAuthority("SCOPE_orders.read")
            .pathMatchers(HttpMethod.POST, "/api/v1/orders")
            .hasAuthority("SCOPE_orders.write")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()))
        .csrf(ServerHttpSecurity.CsrfSpec::disable)
        .build();
}
~~~

**Chỉ tắt CSRF khi API thực sự không dùng cookie/session authentication**. Với ứng dụng browser dùng cookie, cần CSRF protection phù hợp. **TenantAccess** phải lấy tenant từ principal/claims đã xác minh, không tin query/header/body. Service phải filter tenant ở truy vấn. 401 giữ **WWW-Authenticate** theo scheme; 403 không tiết lộ resource khác tenant. Security filter có thể trả lỗi **trước router**, do đó không dựa riêng vào onError để định dạng 401/403. Hạn chế body size, rate limit, CORS origin và tránh token trong URL/log; dữ liệu riêng tư nên dùng no-store/private.

## 15. WebTestClient: kiểm thử route và HTTP contract

**WebTestClient** kiểm tra WebFlux HTTP API, từ status/headers tới JSON body. Có hai cấp kiểm thử:

- **bindToRouterFunction(router)** để test một RouterFunction độc lập, nhanh, phù hợp kiểm tra path/predicate/handler bằng dependency giả.
- **bindToApplicationContext(context)** hoặc test server thật để chạy **SecurityWebFilterChain**, codec, error mapping và beans thực tế. Bind router độc lập **không tự gắn toàn bộ security filter**, nên không thể dùng nó làm bằng chứng xác thực/phân quyền production.

Ví dụ route độc lập:

~~~java
@Test
void healthRouterReturnsJson() {
    RouterFunction<ServerResponse> router =
        RouterFunctions.route(
            RequestPredicates.GET("/health"),
            request -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("status", "UP")));

    WebTestClient.bindToRouterFunction(router)
        .build().get().uri("/health").exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.status").isEqualTo("UP");
}
~~~

Với API có Bearer authentication, dùng test context tích hợp Spring Security và giả lập JWT **có tenant claim + scope được cấp**. Ví dụ dưới đây giả định WebTestClient đã được cấu hình cùng SecurityWebFilterChain:

~~~java
@Test
void postCreatesOrderForAuthorizedTenant() {
    client.mutateWith(mockJwt()
            .jwt(jwt -> jwt.claim("tenant_id", "t-1"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.write")))
        .post().uri("/api/v1/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("productId", "prod-42", "quantity", 2))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().valueMatches(
            "Location", "/api/v1/orders/[^/]+")
        .expectHeader().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON)
        .expectBody().jsonPath("$.quantity").isEqualTo(2);
}
~~~

Test trên cần fixture service/repository và import Spring Security test **mockJwt**. Với môi trường dùng token thực, thêm test xác thực đầy đủ hoặc API test qua HTTP, vì mockJwt không xác minh chữ ký JWT.

| Tình huống | Assertion |
| --- | --- |
| GET đúng ID và tenant | 200 + JSON DTO, no-store |
| GET ID không có hoặc tenant khác | 404, không lộ resource |
| POST hợp lệ | 201, Location, đúng một order |
| Missing/invalid JSON hoặc quantity=0 | 400 với Problem Details |
| POST Content-Type text/plain | 415, không tạo order |
| GET Accept: application/xml | 406 theo negotiation contract |
| Thiếu token/scope | 401 + WWW-Authenticate hoặc 403 phù hợp |
| GET /orders/search so với /orders/{id} | Không nhầm static path với ID |
| limit âm/quá lớn | 400, không lấy unbounded Flux |
| Service ném conflict | 409 với code ổn định |
| Client hủy stream | Publisher/DB operation được hủy/dọn tài nguyên theo contract |
| Concurrent POST cùng business key | Unique constraint ngăn tạo trùng; retry dùng chính sách idempotency |

**StepVerifier** phù hợp để kiểm tra publisher của service, kể cả timeout/retry bằng virtual time khi cần; nó không thay thế WebTestClient cho **status, Content-Type, Location và security**. Không gọi **block()** trong handler chỉ để test dễ hơn.

## 16. OpenAPI 3.1 độc lập cách triển khai

Dù endpoint được viết bằng RouterFunction, HTTP contract vẫn phải mô tả rõ:

~~~yaml
openapi: 3.1.0
info: { title: Orders API, version: 1.0.0 }
paths:
  /api/v1/orders/{id}:
    get:
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string }
      responses:
        '200':
          description: Đơn trong phạm vi được phép xem
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Order' }
        '404': { description: Không tìm thấy/không tiết lộ }
  /api/v1/orders:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: '#/components/schemas/CreateOrder' }
      responses:
        '201':
          description: Đã tạo đơn
          headers:
            Location:
              required: true
              schema: { type: string, format: uri-reference }
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Order' }
        '400': { description: Dữ liệu không hợp lệ }
        '401': { description: Chưa xác thực }
        '403': { description: Không có quyền }
        '406': { description: Accept không hỗ trợ }
        '409': { description: Xung đột }
        '415': { description: Content-Type không hỗ trợ }
components:
  schemas:
    CreateOrder:
      type: object
      required: [productId, quantity]
      properties:
        productId: { type: string }
        quantity: { type: integer, minimum: 1 }
    Order:
      type: object
      properties:
        id: { type: string }
        productId: { type: string }
        quantity: { type: integer }
        status: { type: string }
~~~

Production cần bổ sung **securitySchemes**, JSON Problem Details, GET collection, 429/5xx và schema chi tiết. Không giả định mọi OpenAPI generator tự phát hiện đầy đủ functional routes; test spec-vs-runtime.

## 17. Bài tập và checklist

Thiết kế REST API đa tenant:

~~~text
GET  /api/v1/carts/{id}
GET  /api/v1/carts?limit=20
POST /api/v1/carts
~~~

JSON, Bearer authentication, 201 + Location cho POST, 404 khi resource không có/không được tiết lộ; 400 cho dữ liệu sai, 406/415 cho media type không phù hợp, giới hạn limit tối đa 100.

1. Tạo DTO, **RouterFunction** ba tuyến và **HandlerFunction** dùng ServerRequest/ServerResponse.
2. Viết CartService trả **Mono/Flux**, validate input tường minh và filter theo tenant.
3. Dùng **ProblemDetail** có type/code, giữ authn/authz ở SecurityWebFilterChain.
4. Viết OpenAPI 3.1; tạo tối thiểu **8 WebTestClient tests** cho 200/201/400/401/403/404/406/415, Location và tenant isolation.
5. Kiểm thử concurrent POST/retry sau timeout: chỉ một ý định tạo cart nếu có Idempotency-Key.
6. Xem xét blocking calls, cancellation, backpressure, timeout và resource limits.

**Checklist:** Method/path/predicate có đúng không? 406/415 có bị thành 404 không? Handler có trả Mono, tránh block/subscribe không? JSON có validate? Tenant lấy từ principal? 201/204/404/Location đúng? Lỗi an toàn? WebTestClient có chạy Security filter? OpenAPI khớp runtime?

**Kết luận:** Functional endpoints dùng **RouterFunction → HandlerFunction(ServerRequest) → Mono<ServerResponse>**. Route rõ ràng, pipeline không chặn, kiểm tra quyền và hợp đồng HTTP có kiểm thử là các điều kiện để functional WebFlux hoạt động đúng với REST.




# Đối chiếu cùng hợp đồng HTTP trên Spring MVC và Jakarta REST

## 1. Mục tiêu: hai framework, một giao diện nhìn từ client

Client REST chỉ cần biết **URI, method, status, header, media type, JSON và bảo mật**, không cần biết server viết bằng **Spring MVC** hay **Jakarta REST (JAX-RS)**. Đổi implementation nhưng phá những điều đã hứa với client nghĩa là phá hợp đồng HTTP.

Trong module **INTEGRATION_API_REST**, cùng một hợp đồng tạo/đọc đơn được cài đặt bằng:

- **Spring MVC:** controller dùng @RestController, @GetMapping, @PostMapping, @RequestBody, ResponseEntity; framework xử lý binding, message conversion và exception advice.
- **Jakarta REST:** resource dùng @Path, @GET, @POST, @Consumes, @Produces và jakarta.ws.rs.core.Response; runtime có thể là Jersey, RESTEasy, CXF hoặc implementation tương thích.

Khác nhau ở annotation, bootstrap, security/validation và error mapping, **không phải ý nghĩa GET, POST, 201 hay 404**.

> Mục tiêu: thiết kế một nguồn sự thật OpenAPI/HTTP, dịch từng yêu cầu sang hai cách cài đặt, phân biệt những phần thuộc chuẩn Jakarta REST và những phần phụ thuộc runtime; kiểm chứng bằng cùng một bộ contract tests, bao gồm quyền và retry.

## 2. Chốt hợp đồng HTTP trước khi chọn framework

Giả sử OmniOrder hỗ trợ đọc và tạo đơn thuộc một tenant; các endpoint dưới là **quy ước của API mẫu**, không phải ràng buộc bắt buộc cho mọi dự án.

| Tình huống | HTTP request | HTTP response theo hợp đồng |
|---|---|---|
| Đọc đơn có quyền | GET /api/orders/{id} | 200 JSON |
| Đơn không tồn tại hoặc cố ý che giấu | GET /api/orders/{id} | 404 Problem Details |
| Xem trang đơn | GET /api/orders?limit=20&cursor=... | 200 JSON, nextCursor |
| Tạo một đơn | POST /api/orders, JSON và Idempotency-Key | 201 Created, Location, JSON |
| Input sai | POST JSON lỗi cấu trúc/validation | 400 Problem Details |
| Không đăng nhập hoặc token vô hiệu | Endpoint yêu cầu bearer | 401; challenge phù hợp |
| Không đủ scope/quyền | Endpoint được bảo vệ | 403 hoặc 404 che giấu theo policy |
| Key đã dùng với payload khác | POST Idempotency-Key trùng | 409 Problem Details |
| Tạm không phục vụ được | Database/downstream outage | 5xx; không ngụy trang thành 404 |

**GET phải safe**; POST có side effect cần idempotency; GET dữ liệu riêng tư cần ACL. Status 200 không chứng minh quyền đã được kiểm tra.

### 2.1. HTTP tạo đơn: ví dụ dùng chung cho hai server

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json
Idempotency-Key: intent-741

{
  "customerId": "cus-17",
  "items": [{"sku": "BOOK-01", "quantity": 2}]
}
~~~

Khi yêu cầu hợp lệ và lệnh đã commit:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/ord-741
Content-Type: application/json
Cache-Control: no-store

{"id":"ord-741","status":"PENDING_PAYMENT","totalAmount":350000}
~~~

Retry **cùng tenant/operation/key/payload** sau khi mất response phải nhận outcome đã lưu, **không tạo đơn thứ hai**; cùng key với payload khác trả 409.

### 2.2. GET và lỗi có cấu trúc

~~~http
GET /api/orders/ord-missing HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json

HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Không tìm thấy đơn có thể truy cập",
  "code": "ORDER_NOT_FOUND"
}
~~~

**RFC 9457:** type/title/status/detail/instance là thành viên chuẩn; code là extension. Không trả SQL, stack trace, dữ liệu tenant khác hoặc JWT trong detail.

### 2.3. Bất biến cần giữ khi thay nền tảng

Tối thiểu phải giữ: **đường dẫn và method; required headers/parameters; request/response JSON; HTTP status; Location/Content-Type/Cache-Control; lỗi Problem Details; authentication/authorization; paging order; idempotency và ETag nếu đã công bố**. Chỉ nói “hai endpoint trả cùng object” là chưa đủ để chứng minh cùng hợp đồng HTTP.

## 3. Bảng ánh xạ Spring MVC ↔ Jakarta REST

| Mục đích | Spring MVC | Jakarta REST |
|---|---|---|
| Đánh dấu endpoint/resource | @RestController | @Path trên resource class |
| Path/method | @GetMapping, @PostMapping | @GET, @POST + @Path |
| Media type nhận/trả | consumes/produces | @Consumes/@Produces |
| Biến trong path | @PathVariable | @PathParam |
| Query parameter | @RequestParam | @QueryParam, @DefaultValue |
| Header | @RequestHeader | @HeaderParam |
| JSON body | @RequestBody DTO | DTO entity parameter, không cần @RequestBody |
| Kích hoạt Bean Validation | @Valid / @Validated theo ngữ cảnh | @Valid và Jakarta Validation tích hợp với runtime |
| Status/header/body | ResponseEntity / ResponseStatusException | jakarta.ws.rs.core.Response / WebApplicationException |
| Path/URI context | Servlet/web request | @Context UriInfo, Request, HttpHeaders |
| Xử lý exception | @RestControllerAdvice, @ExceptionHandler | @Provider ExceptionMapper<T> |
| Filter request | Servlet Filter, HandlerInterceptor | ContainerRequestFilter / response filter |
| Security phổ biến | Spring Security FilterChain | Container/Jakarta Security, JWT integration riêng |
| Test framework gần runtime | MockMvc | JerseyTest/RESTEasy integration hoặc HTTP client |

**Namespace:** Jakarta REST dùng **jakarta.ws.rs**, Servlet dùng **jakarta.servlet**, Validation dùng **jakarta.validation**. Spring MVC cũng có thể dùng Jakarta Validation nhưng không vì thế trở thành JAX-RS.

### 3.1. Khởi tạo môi trường khác nhau

Với Spring Boot MVC, starter web tạo và cấu hình DispatcherServlet, message converters và servlet container. Với Jakarta REST, Jakarta REST **là specification**, nên ứng dụng cần một **implementation** đã được tích hợp với Jakarta EE container hoặc servlet runtime. Ví dụ bootstrap Jakarta REST:

~~~java
import jakarta.ws.rs.ApplicationPath;
import jakarta.ws.rs.core.Application;

@ApplicationPath("/api")
public class RestApplication extends Application {}
~~~

@ApplicationPath("/api") cộng @Path("/orders") tạo **/api/orders**, không phải /api/api/orders. Package scanning, JSON provider, validation và security phụ thuộc runtime.

Chạy **hai ứng dụng tách biệt**, dùng chung OpenAPI và test; tránh đăng ký hai controller trùng route.

## 4. Phần dùng chung: DTO, nghiệp vụ và phạm vi quyền

Giữ **DTO và quy tắc nghiệp vụ** độc lập với web framework.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public record OrderItemInput(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity) {}

public record CreateOrderRequest(
        @NotBlank String customerId,
        @NotEmpty List<@Valid OrderItemInput> items) {}

public record OrderView(
        String id, String status, long totalAmount) {}

public record Caller(String subject, String tenant) {}

public interface OrdersUseCase {
    OrderView create(
        Caller caller, String key, CreateOrderRequest request);
    OrderView findVisible(Caller caller, String orderId);
}

class OrderMissing extends RuntimeException {}
class OrderKeyConflict extends RuntimeException {}
~~~

Trong Java thật, **mỗi public top-level type ở một file**. Không dùng JPA entity làm request body để tránh **mass assignment** giá, owner, tenant hoặc trạng thái.

**OrdersUseCase là seam kiến trúc**, phải có implementation, transaction, persistence và exception cụ thể. Hợp đồng gợi ý:

- **findVisible** chỉ tìm dữ liệu tenant/owner đã được xác minh; nếu không thấy, ném **OrderMissing** (domain exception), không trả dữ liệu của tenant khác.
- **create** kiểm tra customer/sku, quy tắc giá, tính hợp lệ trạng thái và Idempotency-Key **trong kho bền vững**; ghi order và outcome idempotency nguyên tử khi phù hợp.
- **Caller** phải được tạo từ **principal/token đã xác minh** của mỗi framework, không lấy tenant từ JSON hoặc một header do client tùy ý khai.
- **DTO constraint** phát hiện quantity=0 và customerId trống; nó không chứng minh customer thuộc tenant, giá đúng hay key chưa được dùng.

Với cùng caller/request, hai implementation phải cho **cùng status/header/JSON**.

## 5. Cài đặt A — Spring MVC

Spring Boot MVC có thể dùng @RestController và ResponseEntity để giữ status/header tường minh. Đây là ví dụ khung với OrdersUseCase từ phần trước:

~~~java
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

interface SpringCallerResolver {
    // Chỉ tạo Caller từ Authentication đã được xác minh.
    Caller resolve(Authentication auth);
}

@RestController
@RequestMapping("/api/orders")
class OrdersMvcController {
    private final OrdersUseCase orders;
    private final SpringCallerResolver callers;

    OrdersMvcController(
            OrdersUseCase orders, SpringCallerResolver callers) {
        this.orders = orders;
        this.callers = callers;
    }

    @PostMapping(consumes = "application/json",
                 produces = "application/json")
    ResponseEntity<OrderView> create(
            @Valid @RequestBody CreateOrderRequest input,
            @RequestHeader("Idempotency-Key") String key,
            Authentication auth) {

        Caller caller = callers.resolve(auth);
        OrderView order = orders.create(caller, key, input);

        return ResponseEntity
            .created(URI.create("/api/orders/" + order.id()))
            .cacheControl(CacheControl.noStore())
            .body(order);
    }

    @GetMapping(path = "/{id}", produces = "application/json")
    ResponseEntity<OrderView> get(
            @PathVariable String id, Authentication auth) {

        OrderView order = orders.findVisible(
            callers.resolve(auth), id);

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(order);
    }
}
~~~

Controller khai URI/method, bind JSON, chạy @Valid, đọc header và tạo **201 + Location** hoặc **200**. Nó chưa có persistence, Spring Security, idempotency ledger, mapping 404/409, pagination hay ETag; **Authentication parameter không tự bảo vệ endpoint**.

### 5.1. Binding và validation đặc trưng Spring

Với quantity=0, @Valid thường dẫn đến **MethodArgumentNotValidException → 400**; JSON không parse được thường là **HttpMessageNotReadableException → 400**, sai Content-Type → **415**. Phải chuẩn hóa error body theo contract.

Nếu muốn mã lỗi riêng:

~~~java
import java.net.URI;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
class OrdersMvcAdvice {
    @ExceptionHandler(OrderMissing.class)
    ResponseEntity<ProblemDetail> missing(OrderMissing ex) {
        ProblemDetail p = ProblemDetail.forStatus(
            HttpStatus.NOT_FOUND);
        p.setType(URI.create(
            "https://api.example.test/problems/order-not-found"));
        p.setTitle("Order not found");
        p.setDetail("Không tìm thấy đơn có thể truy cập");
        p.setProperty("code", "ORDER_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .cacheControl(CacheControl.noStore())
            .body(p);
    }
}
~~~

OrderMissing là **domain exception**; map OrderKeyConflict → 409 và validation → 400 riêng. Advice không tự bao phủ mọi lỗi codec, security filter hoặc DB.

## 6. Cài đặt B — Jakarta REST

Jakarta REST resource dùng @Path và HTTP method annotations; **Response** tạo status, header và entity. Trong cùng ứng dụng Jakarta REST đã có @ApplicationPath("/api"):

~~~java
import jakarta.validation.Valid;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.*;
import java.net.URI;

interface JakartaCallerResolver {
    // Caller từ SecurityContext đã được container kiểm chứng.
    Caller resolve(SecurityContext security);
}

@Path("/orders")
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public class OrdersJakartaResource {
    private final OrdersUseCase orders;
    private final JakartaCallerResolver callers;

    @Context
    SecurityContext security;

    public OrdersJakartaResource(
            OrdersUseCase orders, JakartaCallerResolver callers) {
        this.orders = orders;
        this.callers = callers;
    }

    @POST
    public Response create(
            @Valid CreateOrderRequest input,
            @HeaderParam("Idempotency-Key") String key) {

        Caller caller = callers.resolve(security);
        OrderView order = orders.create(caller, key, input);
        return Response.created(
                URI.create("/api/orders/" + order.id()))
            .header("Cache-Control", "no-store")
            .entity(order)
            .build();
    }

    @GET
    @Path("/{id}")
    public Response get(@PathParam("id") String id) {
        OrderView order = orders.findVisible(
            callers.resolve(security), id);
        return Response.ok(order)
            .header("Cache-Control", "no-store")
            .build();
    }
}
~~~

**Mã minh họa:** cần runtime Jakarta REST, JSON/Validation provider, DI và security. Constructor injection phụ thuộc CDI/container; nếu không được hỗ trợ, đăng ký resource/factory phù hợp.

So với Spring MVC:

- @POST/@GET và @Path định nghĩa operation; **entity parameter** nhận body, không cần @RequestBody.
- @HeaderParam có thể nhận null; kiểm required/format và map 400 rõ ràng.
- @Valid cần Validation integration; **test** để chứng minh.
- @Produces cho response resource; **ExceptionMapper đặt application/problem+json riêng**.
- Response và ResponseEntity cùng vai trò dựng HTTP response nhưng API Java khác nhau.

### 6.1. ExceptionMapper trả đúng Problem Details

~~~java
import jakarta.ws.rs.core.*;
import jakarta.ws.rs.ext.*;
import java.util.Map;

@Provider
public class OrderMissingMapper
        implements ExceptionMapper<OrderMissing> {

    @Override
    public Response toResponse(OrderMissing error) {
        return Response.status(Response.Status.NOT_FOUND)
            .type("application/problem+json")
            .header("Cache-Control", "no-store")
            .entity(Map.of(
                "type",
                "https://api.example.test/problems/order-not-found",
                "title", "Order not found",
                "status", 404,
                "detail", "Không tìm thấy đơn có thể truy cập",
                "code", "ORDER_NOT_FOUND"))
            .build();
    }
}
~~~

Mapper tạo cùng JSON như Spring advice, giả định JSON provider serialize Map. Kiểm tra registration, priority, **Content-Type và body** theo runtime.

Không map mọi Throwable thành 400: outage/bug vẫn là **5xx**, log nội bộ có correlation ID, response không lộ stack trace. Validation/auth thường đi qua provider/filter riêng.

### 6.2. Jakarta REST không phải một server cụ thể

Jersey, RESTEasy, CXF và Jakarta EE server có **JSON, error defaults và DI integration** khác nhau. Kiểm ma trận Jakarta REST/JDK/JSON/Validation/Security cùng thời hạn hỗ trợ.

Annotation portable không bảo đảm JSON giống nhau: cấu hình **null, BigDecimal, date/time, enum** và test schema cả hai.

## 7. Bảo mật: cùng quyền HTTP, hai cách tích hợp

### 7.1. Spring Security với Spring MVC

Khi REST API nhận bearer JWT, Spring Security Resource Server thường triển khai một filter chain để xác thực token và gán authorities. Ví dụ phần cấu hình cốt lõi:

~~~java
// Fragment trong lớp @Configuration có @Bean.
SecurityFilterChain ordersSecurity(HttpSecurity http)
        throws Exception {
    http
        // Chỉ phù hợp nếu API stateless dùng bearer header,
        // không dựa vào cookie/session để xác thực.
        .csrf(csrf -> csrf.disable())
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth -> oauth.jwt(jwt -> {}));
    return http.build();
}
~~~

Fragment cần HttpSecurity, SecurityFilterChain, HttpMethod imports. **JwtDecoder phải kiểm signature/issuer/expiry/audience** và map scopes; không vô hiệu CSRF trong web app dùng cookie/session.

### 7.2. Jakarta REST với container security

Trong Jakarta REST, **SecurityContext** cho biết principal và roles từ security integration của runtime. Resource có thể dùng:

~~~java
import jakarta.annotation.security.RolesAllowed;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.SecurityContext;

// Fragment trong resource class (khi container hỗ trợ role annotations).
@GET
@Path("/{id}")
@RolesAllowed("orders.read")
public Response getAuthorized(
        @PathParam("id") String id,
        @Context SecurityContext context) {

    Caller caller = callers.resolve(context);
    return Response.ok(orders.findVisible(caller, id)).build();
}
~~~

Fragment **thay thế GET mục 6**, không đăng ký hai GET cùng route. @RolesAllowed không tự cài JWT verifier: cần container tích hợp authentication, token/role mapping và enforcement.

Có thể dùng @Provider **ContainerRequestFilter** hoặc container security. Nếu tự set SecurityContext, phải xác minh token trước (không tin Base64 payload). **SecurityContext chuẩn không trực tiếp cung cấp JWT tenant claim**; cần custom principal/identity integration đáng tin. Giữ 401/403 đúng contract.

### 7.3. Cả hai vẫn cần kiểm quyền từng resource

Một token có **orders.read** không mặc nhiên được đọc mọi đơn. Để loại bỏ IDOR/BOLA (Broken Object Level Authorization), cả hai use case phải truyền **Caller đã xác minh**:

~~~sql
SELECT id, status, total_amount
FROM orders
WHERE id = :id
  AND tenant_id = :verified_tenant
  AND owner_subject = :verified_subject;
~~~

Query minh họa; nhóm/ủy quyền có thể cần ACL phức tạp hơn. **Không lấy verified_tenant từ header/query client**. Dùng 403/404 theo chính sách che giấu, có audit.

**Cùng yêu cầu:** sai/thiếu token → 401 với WWW-Authenticate phù hợp; thiếu scope → 403; tenant khác → không tiết lộ order; lỗi auth ở filter → không trả stack trace/PII.

Advice/ExceptionMapper domain không bao phủ chắc chắn lỗi filter trước resource. Muốn 401/403 dùng Problem Details phải cấu hình security handlers riêng và kiểm header challenge.

## 8. Validation, binding và lỗi mặc định: không được giả định giống nhau

### 8.1. Cùng DTO nhưng đường đi khác nhau

Các annotation Jakarta Validation dùng chung, nhưng **cách kích hoạt khi binding** khác nhau:

**Những khác biệt cần test:** Spring @Valid @RequestBody thường trả 400 khi DTO sai; Jakarta @Valid entity parameter cần Validation integration. Spring @RequestHeader required thường bắt thiếu key; Jakarta @HeaderParam có thể nhận null. JSON parse sai nên map 400, Content-Type sai → 415, OrderKeyConflict → 409 và outage DB → 5xx trên **cả hai**.

**Không để default khác nhau thành contract khác nhau.** Chốt 400 + problem+json/code cho input sai; chỉ dùng 422 khi chủ động thiết kế, mô tả và test.

### 8.2. Null, primitive, ngày giờ và số tiền

Muốn phân biệt **thiếu quantity** với **0**, dùng Integer + @NotNull/@Min thay cho primitive int. Tiền cần đơn vị/precision rõ; ngày giờ cần RFC 3339/offset; Jackson và JSON-B không nhất thiết cùng cách biểu diễn null, enum, số.

**Golden JSON fixtures và schema tests** giúp phát hiện sai khác.

## 9. Các HTTP feature nâng cao phải được đối chiếu riêng

### 9.1. Phân trang và cache policy

Nếu GET /api/orders?limit=20&cursor=c-2 đã được công bố, hai framework phải:

- Cùng **limit mặc định/tối đa, cursor, sort ổn định và filter**.
- Cùng schema **items + nextCursor**; danh sách rỗng là **200 với items=[]**.
- Cùng tenant ACL trên mọi page và Cache-Control theo hợp đồng.

Spring dùng @RequestParam, Jakarta REST dùng @QueryParam + @DefaultValue. Trả **collection DTO ổn định**, không lộ kiểu framework-specific như Page<?>.

### 9.2. ETag và conditional GET

Nếu API hỗ trợ cache/revalidation, hai framework có khả năng riêng:

- **Spring MVC:** WebRequest.checkNotModified(etag) hoặc cơ chế conditional response của framework.
- **Jakarta REST:** jakarta.ws.rs.core.Request.evaluatePreconditions(EntityTag), trả ResponseBuilder cho 304 hoặc 412 khi phù hợp.

Ví dụ Jakarta REST (fragment trong GET đã xác thực và kiểm quyền):

~~~java
@Context jakarta.ws.rs.core.Request httpRequest;

public Response getVersioned(String id) {
    Caller caller = callers.resolve(security);
    VersionedOrder found = orders.readVersioned(caller, id);
    EntityTag etag = new EntityTag(found.etagValue());

    Response.ResponseBuilder pre =
        httpRequest.evaluatePreconditions(etag);
    if (pre != null) {
        return pre.tag(etag).build(); // Ví dụ If-None-Match khớp -> 304
    }
    return Response.ok(found.view()).tag(etag).build();
}
~~~

Ở đây VersionedOrder và readVersioned là **API minh họa cần triển khai**, không nằm trong OrdersUseCase tối thiểu. Để tránh trùng route, fragment này thay GET thông thường khi bật ETag. **Kiểm quyền trước khi so ETag**; nếu caller mất quyền, không trả 304 chỉ vì validator khớp. ETag phải gắn với selected representation của user/tenant, không lộ trạng thái tài nguyên người khác.

**304 không body; If-Match sai → 412**. Validator phải tính theo cùng selected representation, không hash object Java tùy tiện.

### 9.3. Idempotency vẫn thuộc tầng nghiệp vụ

Retry POST sau commit không tạo order mới: cả hai framework chỉ đọc header, bảo đảm nằm ở **durable ledger với unique claim, fingerprint, tenant/operation scope và outcome**; không dùng Map trong RAM controller.

Với payment provider, transaction DB không bảo đảm exactly-once ngoài hệ thống: cần provider key/inquiry/reconciliation, công bố TTL key và conflict.

## 10. Một OpenAPI làm hợp đồng tham chiếu

Tách đặc tả HTTP khỏi annotation của mỗi framework để client không phụ thuộc công nghệ server. Ví dụ **OpenAPI 3.1 rút gọn** cho hai operation:

~~~yaml
openapi: 3.1.0
info:
  title: OmniOrder REST API
  version: 1.0.0
security:
  - bearerAuth: []
paths:
  /api/orders:
    post:
      operationId: createOrder
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema: {type: string, minLength: 1, maxLength: 128}
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Order created or saved outcome replayed
          headers:
            Location:
              schema: {type: string, format: uri-reference}
          content:
            application/json:
              schema: {$ref: '#/components/schemas/OrderView'}
        '400': {description: Invalid request}
        '401': {description: Authentication required}
        '403': {description: Forbidden}
        '409': {description: Idempotency or business conflict}
  /api/orders/{id}:
    get:
      operationId: getOrder
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        '200':
          description: Order visible to caller
          content:
            application/json:
              schema: {$ref: '#/components/schemas/OrderView'}
        '401': {description: Authentication required}
        '403': {description: Forbidden}
        '404':
          description: Order absent or hidden
          content:
            application/problem+json:
              schema: {type: object}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer, bearerFormat: JWT}
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerId, items]
      properties:
        customerId: {type: string, minLength: 1}
        items:
          type: array
          minItems: 1
          items:
            type: object
            required: [sku, quantity]
            properties:
              sku: {type: string, minLength: 1}
              quantity: {type: integer, minimum: 1}
    OrderView:
      type: object
      required: [id, status, totalAmount]
      properties:
        id: {type: string}
        status: {type: string}
        totalAmount: {type: integer, format: int64}
~~~

OAS này **tối giản**: trước khi phát hành cần bổ sung Problem Details schema, giới hạn key, paging, ETag, security scopes và response thực tế. OAS không tự thực thi safe GET hay quyền tenant.

## 11. Kiểm thử cùng một hợp đồng với hai server

### 11.1. Ma trận black-box dùng chung

| Test HTTP từ client | Spring MVC | Jakarta REST |
|---|---|---|
| POST đúng JSON + key + token | 201, Location, JSON đúng schema | **Phải giống** |
| POST JSON thiếu items/quantity=0 | 400 Problem Details | **Phải giống** |
| POST thiếu Idempotency-Key | 400 theo contract | **Phải giống**, dù @HeaderParam cho null |
| POST lại cùng key/payload sau mất response | Cùng order ID, chỉ một business effect | **Phải giống** |
| POST cùng key nhưng payload khác | 409, cùng error code | **Phải giống** |
| GET ID hiện hữu cùng tenant | 200, body đúng schema | **Phải giống** |
| GET ID không có/tenant khác | 404 theo policy, không lộ data | **Phải giống** |
| Thiếu/sai token, scope thiếu | 401/403 và challenge phù hợp | **Phải giống** |
| GET collection không có dữ liệu | 200, items=[] | **Phải giống** |
| GET với validator phù hợp nếu hỗ trợ | 304 không body, quyền vẫn được kiểm | **Phải giống** |
| DB timeout hoặc dependency outage | 5xx và detail an toàn | **Phải giống** |

Assert **Location, media type, JSON schema, error code, ACL và side effects**, không chỉ status.

### 11.2. Hai lớp test bổ sung nhau

**Framework-specific:** Spring dùng **MockMvc**; Jakarta dùng JerseyTest/RESTEasy integration để kiểm provider, CDI, security và mapper. Unit test gọi trực tiếp method **không chứng minh HTTP behavior**.

**Framework-neutral:** cùng một bộ JUnit/Java HttpClient chạy với **base URL của hai server**:

~~~java
// Test fixture khởi tạo baseUri, token hợp lệ và test data độc lập
// cho TỪNG server; cùng hàm này chạy cho cả hai.
void verifyCreateOrder(URI baseUri, String testToken)
        throws Exception {
    String json = """
        {"customerId":"cus-17",
         "items":[{"sku":"BOOK-01","quantity":2}]}
        """;
    HttpRequest req = HttpRequest.newBuilder(
            baseUri.resolve("/api/orders"))
        .header("Authorization", "Bearer " + testToken)
        .header("Idempotency-Key", "test-intent-741")
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(json))
        .build();
    HttpResponse<String> response =
        HttpClient.newHttpClient().send(
            req, HttpResponse.BodyHandlers.ofString());

    assertEquals(201, response.statusCode());
    String location = response.headers()
        .firstValue("Location").orElseThrow();
    assertTrue(URI.create(location).getPath()
        .startsWith("/api/orders/"));
    // Tiếp tục assert JSON schema, số bản ghi và replay response.
}
~~~

Fragment cần imports java.net.URI, java.net.http.*, JUnit assertions và fixtures. **Không dùng production token** hoặc giả định hai server chia sẻ dữ liệu/ID. Kiểm tra path của Location để chấp nhận cả relative/absolute URI, rồi kiểm response schema/replay.

### 11.3. Điều gì có thể khác mà không phá contract?

Tên class, framework exception, dependency injection, cache/repository implementation, thứ tự property JSON **nếu client đọc JSON theo schema chứ không yêu cầu byte-identical**. Không mặc định sự khác biệt về **status, content type, nullability, error code, ACL, Retry-After hoặc ETag** là vô hại.

## 12. Bài tập và checklist

**Bài 1.** Spring @PostMapping trả 201 + Location; Jakarta @POST trả 200 JSON. Có cùng hợp đồng không? **Đáp án:** Không; dùng Response.created(...).entity(...).build() và kiểm thử Location/status.

**Bài 2.** Spring @RequestHeader bắt thiếu key là lỗi 400; Jakarta @HeaderParam nhận null rồi tạo đơn. **Đáp án:** Thêm validation rõ ở boundary/service Jakarta, cùng Problem Details 400, không chạy side effect.

**Bài 3.** Hai server đều xác thực JWT, nhưng Jakarta cho đọc order tenant khác nếu biết ID. **Đáp án:** Scope/đăng nhập không đủ; truy vấn/service phải giới hạn verified tenant và owner. Thêm negative integration test.

**Bài 4.** Jakarta GET trả 304 khi If-None-Match khớp, nhưng token đã mất quyền truy cập. **Đáp án:** Sai; kiểm quyền trước evaluatePreconditions, 304 không được tiết lộ tài nguyên còn tồn tại cho caller trái quyền.

**Bài 5.** SDK sinh từ OpenAPI hoạt động với Spring nhưng không deserialize JSON từ Jakarta sau khi đổi provider. **Đáp án:** Chốt serialization schema (date/number/null/enum), cùng contract test, không coi lỗi là “khác framework không tránh được”.

Checklist bàn giao:

- [ ] Một OpenAPI/HTTP contract làm nguồn sự thật, không để annotation tự quyết định giao diện?
- [ ] URI, method, status, Location, media type và response schema khớp?
- [ ] Spring @Valid/@RequestBody và Jakarta @Valid/entity được kiểm chứng bằng request lỗi?
- [ ] Spring advice và Jakarta ExceptionMapper trả **cùng Problem Details**?
- [ ] Authentication và authorization **mức tài nguyên** được kiểm thử trên cả hai?
- [ ] Pagination, cache/ETag và idempotency có cùng ngữ nghĩa khi đã công bố?
- [ ] Hai app chạy bộ black-box tests giống nhau, ngoài test riêng của từng runtime?

**Kết luận:** Spring MVC và Jakarta REST là **hai cách triển khai**, còn HTTP contract là **cam kết với client**. Khi DTO, nghiệp vụ và quyền truy cập được thiết kế rõ, cả hai đều có thể trả cùng 201/404/409, JSON và Problem Details. Giá trị của phép đối chiếu không nằm ở tên annotation tương ứng, mà ở **kiểm thử cho thấy hành vi công khai không thay đổi khi thay framework**.

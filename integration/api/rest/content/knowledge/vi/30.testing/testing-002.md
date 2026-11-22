# MockMvc cho Spring MVC và WebTestClient cho reactive API

## 1. Kiểm thử HTTP contract, không chỉ gọi phương thức Java

Một REST API có thể trả đúng đối tượng khi gọi service trực tiếp nhưng vẫn sai ở biên HTTP: GET sai URI, POST không kích hoạt Bean Validation, status 200 thay vì 201, thiếu Location, Content-Type không đúng, header cache bị mất, hoặc filter bảo mật để lộ đơn của tenant khác.

Trong module **INTEGRATION_API_REST**, người học phải kiểm tra sự kết hợp của resource/URI, phương thức, mã trạng thái HTTP, phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền và cách xử lý lỗi. Với Java/Spring, hai công cụ quan trọng là:

- **MockMvc**: mô phỏng HTTP request qua **Spring MVC DispatcherServlet** trong Servlet stack, không cần khởi động cổng mạng.
- **WebTestClient**: HTTP-style test client, đặc biệt hữu ích cho **Spring WebFlux** và các response **Mono/Flux**, có thể bind trực tiếp vào WebFlux application hoặc gọi server thật bằng HTTP.

**Đừng đồng nhất tên test client với loại ứng dụng:** WebTestClient còn có khả năng kiểm thử Spring MVC qua adapter như **MockMvcWebTestClient** trong Spring Test. Khác biệt cốt lõi của bài này là **MVC xử lý Servlet request** còn **WebFlux sử dụng reactive request-processing**, mỗi stack cần kiểm tra đúng filter, validation, error handling và asynchronous behavior của mình.

> **Tiêu chí hoàn thành:** Một test HTTP phải có *request được khai báo rõ*, *kết quả HTTP quan sát được*, *negative cases* và *bất biến nghiệp vụ/bảo mật được kiểm tra tại tầng phù hợp*. Một test trả 200 chưa đủ để kết luận endpoint an toàn hay hợp đồng API đúng.

### 1.1. Ví dụ hợp đồng dùng xuyên suốt

Ứng dụng OmniOrder có hai endpoint riêng tư:

~~~http
GET /api/orders/ord-17 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Khi người gọi được phép xem đơn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v3"
Cache-Control: no-store

{"id":"ord-17","status":"CONFIRMED","totalAmount":350000}
~~~

Với POST tạo đơn:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: checkout-17

{"customerId":"cus-17","items":[{"sku":"BOOK-01","quantity":2}]}
~~~

Một kết quả thành công được thiết kế là **201 Created + Location**; body chứa ID, trạng thái và tổng tiền do server tính. Nếu DTO sai, trả **400**; ID không có hoặc bị che theo quyền, trả **404**; thiếu token **401**; thiếu scope **403**; cùng idempotency key với payload khác **409**. Những quy tắc này là **hợp đồng của API mẫu**, cần nhất quán giữa tài liệu, code và test.

## 2. Chọn tầng kiểm thử trước khi chọn annotation

| Tầng | Công cụ/cách chạy | Chứng minh được | Chưa chứng minh |
|---|---|---|---|
| **Unit test** | JUnit, Mockito, StepVerifier | Logic domain, mapper, reactive signals | URL mapping, JSON codec, HTTP filters |
| **MVC slice** | @WebMvcTest + MockMvc | Mapping, validation, advice, JSON, filter được nạp | Repository/DB/gateway thật |
| **MVC application** | @SpringBootTest + @AutoConfigureMockMvc | Spring context và Servlet filter chain được cấu hình | TCP/TLS/proxy/cổng mạng thật |
| **WebFlux slice** | @WebFluxTest + WebTestClient | Reactive controller, codecs, advice, WebFilter đã nạp | Hạ tầng/DB/downstream thật |
| **WebFlux server** | @SpringBootTest(RANDOM_PORT) + WebTestClient.bindToServer | HTTP qua cổng server, serialization/response commit | CDN, WAF, gateway nếu không đi qua chúng |
| **End-to-end** | Client HTTP/browser qua tuyến triển khai | Routing, gateway, security, CORS, response thực | Mọi race/failure nếu không fault inject |

**Slice test nhanh nhưng có chủ đích thiếu bean.** Chúng dễ kiểm lỗi controller nhưng không thể thay thế test transaction, uniqueness, tenant SQL predicate hoặc idempotency dưới đồng thời. Nếu cần xác thực JWT thật, phải có kiểm thử cấu hình decoder/issuer/audience, không chỉ tạo principal giả.

### 2.1. Những trạng thái cần assert

| Kết quả | Test nên nhìn vào |
|---|---|
| **200 OK** | JSON fields/types, Content-Type, cache/ETag khi được công bố |
| **201 Created** | Status, Location, body, chỉ một business effect |
| **204 No Content** | Body rỗng; không tự suy đoán body null |
| **400 Bad Request** | DTO/JSON sai, Problem Details, không gọi service |
| **401/403** | Authentication/scope; không lộ resource hoặc token |
| **404 Not Found** | Không có hoặc không được phép thấy theo policy |
| **409/412** | Xung đột/idempotency, optimistic version/If-Match |
| **429/503** | Retry-After và retry policy khi API công bố |
| **304 Not Modified** | ETag match sau khi đã kiểm quyền, không có body |

Không assert toàn bộ error detail được dịch hoặc message của thư viện làm giao diện máy đọc; ưu tiên **status, type/code ổn định và invalid field paths**.

## 3. DTO và service contract dùng cho ví dụ

Để các đoạn mã dễ đối chiếu, dùng DTO Java record với Jakarta Bean Validation:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

record ItemInput(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity) {}

record CreateOrderRequest(
        @NotBlank String customerId,
        @NotEmpty List<@Valid ItemInput> items) {}

record OrderView(String id, String status, long totalAmount) {}

class OrderNotVisible extends RuntimeException {}
class OrderConflict extends RuntimeException {}
~~~

Các đoạn mã trong bài là **fragments đặt trong những ứng dụng/test classes tách biệt**, không ghép tất cả controller có cùng URI vào một Spring context. Với mã Java thật, phải bố trí top-level classes/visibility/imports đúng và cấu hình persistence/security. **Integer + @NotNull** giúp phát hiện quantity bị bỏ trống; **@Valid trên phần tử List** kích hoạt kiểm ràng buộc lồng nhau.

Ở các ví dụ, tenant ID được lấy từ **principal JWT đã xác minh** của security stack, không từ request body/header tùy tiện. Repository/service phải giới hạn theo tenant/owner; MockMvc và WebTestClient chỉ chứng minh điều đó nếu fixture thực sự chứa nhiều tenant hoặc mock expectation phù hợp.

## 4. MockMvc: kiểm Spring MVC request tới response

### 4.1. Controller MVC mẫu

~~~java
import java.net.URI;
import java.util.Optional;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;

interface MvcOrdersService {
    Optional<OrderView> findVisible(String id, String tenant);
    OrderView create(CreateOrderRequest request, String tenant, String key);
}

@RestController
@RequestMapping("/api/orders")
class OrdersMvcController {
    private final MvcOrdersService orders;

    OrdersMvcController(MvcOrdersService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        OrderView view = orders.findVisible(id, requiredTenant(jwt))
            .orElseThrow(OrderNotVisible::new);
        return ResponseEntity.ok()
            .eTag("\"order-v3\"") // Chỉ minh họa; ETag thật theo version
            .cacheControl(CacheControl.noStore())
            .body(view);
    }

    @PostMapping(consumes = "application/json")
    ResponseEntity<OrderView> create(
            @Valid @RequestBody CreateOrderRequest request,
            @RequestHeader("Idempotency-Key") String key,
            @AuthenticationPrincipal Jwt jwt) {
        OrderView view = orders.create(
            request, requiredTenant(jwt), key);
        return ResponseEntity.created(
                URI.create("/api/orders/" + view.id()))
            .cacheControl(CacheControl.noStore())
            .body(view);
    }

    private String requiredTenant(Jwt jwt) {
        if (jwt == null || jwt.getClaimAsString("tenant_id") == null) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Tenant context missing");
        }
        return jwt.getClaimAsString("tenant_id");
    }
}
~~~

Controller chỉ minh họa **HTTP boundary**: ETag phải lấy từ version/representation thật; **@Valid không bảo vệ quyền owner**; service phải triển khai idempotency bền vững. Cặp ETag + **Cache-Control: no-store** trong ví dụ chỉ để minh họa việc assert headers: no-store không phù hợp nếu muốn browser tự lưu bản thể để revalidate. Khi thiết kế cache có điều kiện thật, cân nhắc **private, no-cache** cùng ETag/If-None-Match, kiểm quyền trước khi trả 304 và bảo đảm cache không chia sẻ sai tenant. Khi chưa có JWT resource-server configuration, @AuthenticationPrincipal không tự xác minh token; lỗi thiếu tenant phải được xử lý như lỗi authorization, không leak claim details.

### 4.2. Xử lý lỗi bằng Problem Details

~~~java
import java.net.URI;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.bind.MethodArgumentNotValidException;

@RestControllerAdvice
class MvcOrdersAdvice {
    @ExceptionHandler(OrderNotVisible.class)
    ResponseEntity<ProblemDetail> notFound() {
        ProblemDetail p = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        p.setType(URI.create(
            "https://api.example.test/problems/order-not-found"));
        p.setTitle("Order not found");
        p.setProperty("code", "ORDER_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(p);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> invalid(
            MethodArgumentNotValidException ex) {
        ProblemDetail p = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        p.setTitle("Invalid request");
        p.setProperty("code", "VALIDATION_FAILED");
        p.setProperty("invalidParams", ex.getFieldErrors().stream()
            .limit(20)
            .map(e -> e.getField())
            .toList());
        return ResponseEntity.badRequest()
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(p);
    }
}
~~~

**invalidParams** là extension do API mẫu định nghĩa; ví dụ lưu **đường dẫn field**, không serialise rejectedValue có thể chứa PII. Lỗi JSON không parse được có thể là **HttpMessageNotReadableException** với 400; cần handler/test riêng nếu contract đòi mã MALFORMED_JSON. Security filter có thể phát 401/403 **ngoài controller advice**; chúng cần cấu hình và kiểm tra riêng.

### 4.3. Cấu hình test Spring MVC

Hai đường thử phổ biến:

~~~java
// Nhanh, tập trung controller/MVC. Nạp advice và security có chủ đích:
@WebMvcTest(OrdersMvcController.class)
@Import({MvcOrdersAdvice.class, ApiSecurityConfig.class})
class OrdersMvcSliceTest { /* @Autowired MockMvc, service mock... */ }

// Context ứng dụng rộng hơn; dùng filter chain thực của Spring:
@SpringBootTest
@AutoConfigureMockMvc
class OrdersMvcApplicationTest { /* @Autowired MockMvc... */ }
~~~

Ví dụ **ApiSecurityConfig** là cấu hình của project, phải thực thi JWT validation và scope. Trong slice test, bean **JwtDecoder** có thể cần mock hoặc cấu hình thêm nếu SecurityFilterChain đòi nó. Với Spring Framework **6.2+ / Spring Boot 3.4+**, dùng **@MockitoBean** trong test để override dependency; dự án Boot cũ có thể dùng @MockBean với lưu ý API/khả năng hỗ trợ theo phiên bản. Không tự thêm dependencies hoặc thay đổi project vì bài học này.

MockMvc cũng hỗ trợ hai cách tạo thủ công: **MockMvcBuilders.standaloneSetup(controller)** và **webAppContextSetup(context)**. Standalone setup không tự có tất cả filter/advice/mapping của production: phải đăng ký chúng có chủ đích; nó phù hợp test controller nhanh, **không phù hợp để kết luận Spring Security đang bảo vệ endpoint** chỉ từ kết quả 200.

### 4.4. Kiểm GET 200, JSON, header và tenant

Fragment trong test class có MockMvc và Mockito:

~~~java
@Autowired MockMvc mvc;
@MockitoBean MvcOrdersService orders;

@Test
void readsVisibleOrder() throws Exception {
    given(orders.findVisible("ord-17", "tenant-A"))
        .willReturn(Optional.of(
            new OrderView("ord-17", "CONFIRMED", 350000)));

    mvc.perform(get("/api/orders/{id}", "ord-17")
            .with(jwt()
                .jwt(j -> j.subject("buyer-17")
                    .claim("tenant_id", "tenant-A"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.read")))
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(header().string("ETag", "\"order-v3\""))
        .andExpect(header().string("Cache-Control", "no-store"))
        .andExpect(jsonPath("$.id").value("ord-17"))
        .andExpect(jsonPath("$.totalAmount").value(350000));

    verify(orders).findVisible("ord-17", "tenant-A");
}
~~~

Imports cần có từ JUnit 5, MockMvcRequestBuilders/ResultMatchers, Mockito BDD/verify, Spring Security Test và Spring HTTP. **jwt() tạo principal giả cho HTTP security tests**; nó không kiểm chữ ký, issuer, audience, expiration hoặc public key của token thật. Những kiểm thử đó cần **JwtDecoder thật hoặc integration test** phù hợp.

### 4.5. Kiểm POST 201 và invalid DTO không chạy nghiệp vụ

~~~java
@Test
void createsOrder() throws Exception {
    given(orders.create(any(CreateOrderRequest.class),
            eq("tenant-A"), eq("checkout-17")))
        .willReturn(new OrderView("ord-17", "CREATED", 350000));

    mvc.perform(post("/api/orders")
            .with(jwt()
                .jwt(j -> j.claim("tenant_id", "tenant-A"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.create")))
            .contentType(MediaType.APPLICATION_JSON)
            .header("Idempotency-Key", "checkout-17")
            .content("""
                {"customerId":"cus-17",
                 "items":[{"sku":"BOOK-01","quantity":2}]}
                """))
        .andExpect(status().isCreated())
        .andExpect(header().string(
            "Location", "/api/orders/ord-17"))
        .andExpect(jsonPath("$.status").value("CREATED"));
}

@Test
void rejectsInvalidNestedQuantity() throws Exception {
    mvc.perform(post("/api/orders")
            .with(jwt()
                .jwt(j -> j.claim("tenant_id", "tenant-A"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.create")))
            .header("Idempotency-Key", "checkout-bad")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"customerId":"cus-17",
                 "items":[{"sku":"BOOK-01","quantity":0}]}
                """))
        .andExpect(status().isBadRequest())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON))
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.invalidParams").isArray());

    verifyNoInteractions(orders);
}
~~~

Trong REST API với **cookie/session authentication**, POST có thể cần **.with(csrf())** theo Spring Security Test; với API bearer-only stateless, quyết định tắt CSRF phụ thuộc cấu hình bảo mật thật. Không thêm csrf() chỉ để ép test xanh khi production đang có lỗ hổng hoặc vô hiệu CSRF vô điều kiện cho mọi ứng dụng browser.

Lưu ý: test **201 + Location** chưa chứng minh idempotency. Phải gửi cùng key/payload hai lần qua **database-backed integration test** và assert chỉ có một order; key trùng payload khác phải trả conflict đúng hợp đồng.

### 4.6. Kiểm 401, 403, 404 và không lộ dữ liệu

~~~java
@Test
void rejectsUnauthorizedAndWrongScope() throws Exception {
    mvc.perform(get("/api/orders/ord-17"))
        .andExpect(status().isUnauthorized());

    mvc.perform(get("/api/orders/ord-17")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_other"))))
        .andExpect(status().isForbidden());

    verifyNoInteractions(orders);
}

@Test
void hidesOrderOutsideTenant() throws Exception {
    given(orders.findVisible("ord-secret", "tenant-A"))
        .willReturn(Optional.empty());

    mvc.perform(get("/api/orders/ord-secret")
            .with(jwt()
                .jwt(j -> j.claim("tenant_id", "tenant-A"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.read"))))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
}
~~~

**Giới hạn của mock:** trả Optional.empty() từ Mockito chỉ chứng minh controller map empty → 404, **không chứng minh SQL truy vấn lọc tenant đúng**. Phải thêm integration test với hai tenants có bản ghi thật và kiểm phản hồi/side effect. Để kiểm 401/403, đảm bảo **Spring Security filter chain đã được nạp**; standaloneSetup đơn độc có thể không có filter.

### 4.7. Controller MVC chạy bất đồng bộ: cần asyncDispatch

MockMvc mô phỏng Servlet API, nên controller trả **Callable**, **DeferredResult** hoặc dạng async Servlet có thể cần hai bước:

~~~java
MvcResult started = mvc.perform(get("/api/async-report")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(started))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.state").value("DONE"));
~~~

Đây là test fragment cho một async MVC endpoint **đã được định nghĩa ở ứng dụng**. MockMvc không tự chứng minh hành vi timeout/connection disconnect của socket thật; cần test riêng. **Không nhầm async MVC với WebFlux**: một Servlet controller dùng DeferredResult không tự biến request stack thành reactive runtime.

## 5. WebTestClient: HTTP assertions trên Spring WebFlux

**WebTestClient** có API request builder và expectation tương tự MockMvc, nhưng dành cho **reactive web stack** và còn hỗ trợ kiểm các publisher trả dữ liệu theo thời gian. WebTestClient không yêu cầu client test phải dùng WebClient production; nó cung cấp một giao diện HTTP kiểm thử.

### 5.1. Chọn binding đúng mục tiêu

~~~java
// Chỉ controller/handler, chủ động cấu hình collaborators:
WebTestClient client = WebTestClient
    .bindToController(controller)
    .controllerAdvice(problemAdvice)
    .build();

// Bind tới reactive ApplicationContext đã có codecs/WebFilters:
WebTestClient client2 = WebTestClient
    .bindToApplicationContext(applicationContext)
    .build();

// Gọi HTTP server thật (phải khởi động server ở cổng phù hợp):
WebTestClient client3 = WebTestClient
    .bindToServer()
    .baseUrl("http://localhost:8080")
    .build();
~~~

Các ví dụ **là ba cách thiết lập thay thế**, không nên dùng tất cả cùng tên client trong một test. Có thể dùng **bindToRouterFunction(routerFunction)** khi API viết theo functional endpoints. Bind-to-controller/context sử dụng **mock server exchange**, không mở socket; bind-to-server gửi HTTP thật, vì vậy phù hợp kiểm header, encoding và network behavior hơn nhưng cần test fixture/port.

Một cách dùng phổ biến với Spring Boot:

~~~java
// Slice, chỉ nạp WebFlux controller và những bean được import.
@WebFluxTest(controllers = OrdersReactiveController.class)
class OrdersReactiveSliceTest {
    @Autowired WebTestClient client;
    @MockitoBean ReactiveOrdersService orders;
}

// Toàn reactive server trên cổng ngẫu nhiên, kiểm qua HTTP thật.
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrdersReactiveServerTest {
    @LocalServerPort int port;

    WebTestClient client() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();
    }
}
~~~

**Điều kiện:** ứng dụng phải thật sự dùng reactive WebFlux server, không bị starter Servlet MVC chiếm ưu tiên ngoài ý định; import/advice/security và các test dependencies phải đúng phiên bản. Nếu cần test SecurityWebFilterChain bằng client mock-bound, phải nạp security config/filter tương ứng; **@WebFluxTest không tự nạp toàn bộ repository, HTTP clients hoặc các @Component tùy ý**.

### 5.2. Reactive controller mẫu

Đây là **ứng dụng minh họa khác** với OrdersMvcController ở mục 4, cùng JSON/HTTP contract nhưng service trả Mono:

~~~java
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

interface ReactiveOrdersService {
    // Mono.empty() nghĩa là không tìm thấy order được phép đọc.
    // Lỗi database phải phát onError, KHÔNG trả empty.
    Mono<OrderView> findVisible(String id, String tenant);
    Mono<OrderView> create(
        CreateOrderRequest request, String tenant, String key);
}

@RestController
@RequestMapping("/api/orders")
class OrdersReactiveController {
    private final ReactiveOrdersService orders;
    OrdersReactiveController(ReactiveOrdersService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderView>> get(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        String tenant = requiredTenant(jwt);
        return orders.findVisible(id, tenant)
            .switchIfEmpty(Mono.error(new OrderNotVisible()))
            .map(view -> ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(view));
    }

    @PostMapping(consumes = "application/json")
    Mono<ResponseEntity<OrderView>> create(
            @Valid @RequestBody Mono<CreateOrderRequest> request,
            @RequestHeader("Idempotency-Key") String key,
            @AuthenticationPrincipal Jwt jwt) {
        String tenant = requiredTenant(jwt);
        return request
            .flatMap(dto -> orders.create(dto, tenant, key))
            .map(view -> ResponseEntity.created(
                URI.create("/api/orders/" + view.id()))
                .body(view));
    }

    private String requiredTenant(Jwt jwt) {
        if (jwt == null || jwt.getClaimAsString("tenant_id") == null) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Tenant context missing");
        }
        return jwt.getClaimAsString("tenant_id");
    }
}
~~~

**Không gọi block() hoặc subscribe() thủ công trong controller.** WebFlux quản lý subscription; **onError** đi qua pipeline xử lý lỗi khi response chưa commit. Nếu service trả Mono.empty() ở GET, switchIfEmpty chuyển thành 404 theo contract; nếu database lỗi, **không dùng onErrorResume(error -> Mono.empty())** để biến outage thành 404.

### 5.3. Advice WebFlux khác kiểu exception của MVC

~~~java
import java.net.URI;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.bind.support.WebExchangeBindException;

@RestControllerAdvice
class ReactiveOrdersAdvice {
    @ExceptionHandler(OrderNotVisible.class)
    ResponseEntity<ProblemDetail> missing() {
        ProblemDetail p = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        p.setType(URI.create(
            "https://api.example.test/problems/order-not-found"));
        p.setTitle("Order not found");
        p.setProperty("code", "ORDER_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(p);
    }

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<ProblemDetail> invalid(
            WebExchangeBindException ex) {
        ProblemDetail p = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        p.setProperty("code", "VALIDATION_FAILED");
        p.setProperty("invalidParams", ex.getFieldErrors().stream()
            .limit(20).map(e -> e.getField()).toList());
        return ResponseEntity.badRequest()
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(p);
    }
}
~~~

Trong Spring MVC, input validation thường phát **MethodArgumentNotValidException**. Trong WebFlux, request body validation thường phát **WebExchangeBindException**; method-level validation hoặc JSON decoding có thể đi qua exception khác tùy Spring version. **Không dùng một advice bắt mọi Throwable → 400**: lỗi server, response value sai, timeout hoặc serialization phải được phân loại thành đúng 5xx/4xx.

### 5.4. WebTestClient kiểm Mono và HTTP

Fragment trong @WebFluxTest đã cấu hình service mock:

~~~java
@Test
void reactiveGetReturnsOrder() {
    given(orders.findVisible("ord-17", "tenant-A"))
        .willReturn(Mono.just(
            new OrderView("ord-17", "CONFIRMED", 350000)));

    client.mutateWith(mockJwt()
            .jwt(j -> j.subject("buyer-17")
                .claim("tenant_id", "tenant-A"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.read")))
        .get().uri("/api/orders/{id}", "ord-17")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo("ord-17")
        .jsonPath("$.totalAmount").isEqualTo(350000);
}

@Test
void reactiveEmptyBecomes404() {
    given(orders.findVisible("ord-secret", "tenant-A"))
        .willReturn(Mono.empty());

    client.mutateWith(mockJwt()
            .jwt(j -> j.claim("tenant_id", "tenant-A"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.read")))
        .get().uri("/api/orders/ord-secret")
        .exchange()
        .expectStatus().isNotFound()
        .expectHeader().contentTypeCompatibleWith(
            MediaType.APPLICATION_PROBLEM_JSON)
        .expectBody()
        .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND");
}
~~~

**mockJwt()** ở đây là **SecurityMockServerConfigurers.mockJwt()** cho **mock-bound WebTestClient**, không phải **SecurityMockMvcRequestPostProcessors.jwt()** của MockMvc. Cần **spring-security-test** và WebFlux SecurityWebFilterChain thực sự được cài vào test exchange; một WebTestClient tạo trực tiếp từ controller mà không apply security configurer/filter không kiểm chứng được 401/403.

### 5.5. POST thành công, validation và service side effects

~~~java
@Test
void reactiveInvalidInputDoesNotReachService() {
    client.mutateWith(mockJwt()
            .jwt(j -> j.claim("tenant_id", "tenant-A"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.create")))
        .post().uri("/api/orders")
        .header("Idempotency-Key", "checkout-bad")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("""
            {"customerId":"cus-17",
             "items":[{"sku":"BOOK-01","quantity":0}]}
            """)
        .exchange()
        .expectStatus().isBadRequest()
        .expectBody()
        .jsonPath("$.code").isEqualTo("VALIDATION_FAILED");

    verifyNoInteractions(orders);
}

@Test
void reactivePostReturns201AndLocation() {
    given(orders.create(any(CreateOrderRequest.class),
            eq("tenant-A"), eq("checkout-17")))
        .willReturn(Mono.just(
            new OrderView("ord-17", "CREATED", 350000)));

    client.mutateWith(mockJwt()
            .jwt(j -> j.claim("tenant_id", "tenant-A"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.create")))
        .post().uri("/api/orders")
        .header("Idempotency-Key", "checkout-17")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("""
            {"customerId":"cus-17",
             "items":[{"sku":"BOOK-01","quantity":2}]}
            """)
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().valueEquals(
            "Location", "/api/orders/ord-17")
        .expectBody()
        .jsonPath("$.id").isEqualTo("ord-17");
}
~~~

**@Valid @RequestBody Mono<CreateOrderRequest>** có thể phát validation error trong publisher sau khi decode body. Test trên kiểm trọn HTTP pipeline, không chỉ gọi Validator. Kiểm thêm JSON malformed, thiếu header bắt buộc, Content-Type sai (415), item null và list quá dài nếu DTO quy định giới hạn.

Khi test **security method invocation** trong reactive service, Spring Security có thể cần **@EnableReactiveMethodSecurity** và Reactor Context hợp lệ. Đừng giả định @EnableMethodSecurity của Servlet stack kiểm mọi reactive publisher giống nhau.

## 6. Stream Flux, SSE và StepVerifier: không chỉ kiểm một JSON body

Một Mono trả tối đa một phần tử; Flux có thể phát nhiều phần tử, bị hủy hoặc lỗi sau khi đã gửi dữ liệu. Nếu HTTP response **đã commit header/status**, server không thể thay 200 thành 500 rồi ghi một Problem Details JSON mới.

### 6.1. Ví dụ Server-Sent Events (SSE)

~~~java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;

@GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<String>> orderEvents() {
    return Flux.interval(Duration.ofMillis(50))
        .map(n -> ServerSentEvent.<String>builder()
            .id(Long.toString(n))
            .event("heartbeat")
            .data("alive")
            .build());
}
~~~

Fragment này cần đặt trong reactive controller. Nó tạo stream vô hạn để minh họa **cancel**, không phải mẫu nên phát vô hạn vào production: phải xét connection limits, heartbeat, authorization lifetime, backpressure/resource cleanup và client reconnect.

### 6.2. WebTestClient kết hợp StepVerifier

~~~java
var result = client.get()
    .uri("/api/orders/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(
        MediaType.TEXT_EVENT_STREAM)
    .returnResult(
        new ParameterizedTypeReference<ServerSentEvent<String>>() {});

StepVerifier.create(result.getResponseBody())
    .assertNext(event -> {
        assertEquals("heartbeat", event.event());
        assertEquals("alive", event.data());
    })
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

**Quan trọng:** WebTestClient đã xác nhận **HTTP status + Content-Type**; StepVerifier kiểm **dòng dữ liệu/cancel** của response Flux. Không dùng **expectBody(String.class)** để đợi stream vô hạn hoàn thành. Test streaming nên có timeout thực thi ngắn, deterministic scheduler khi kiểm logic thời gian và fixture cleanup rõ.

Nếu service trả **Flux.error(ex)** trước khi response commit, cơ chế lỗi có thể tạo 5xx Problem Details. Nếu đã phát một SSE event rồi mới lỗi, **status/header 200 không thể đổi**; test đúng kết nối bị đóng hoặc event lỗi trong giao thức SSE đã được định nghĩa, thay vì assert body 500 như request thông thường.

### 6.3. StepVerifier còn hữu ích ở service layer

~~~java
StepVerifier.create(
        reactiveOrders.findVisible("ord-secret", "tenant-A"))
    .verifyComplete(); // Hợp đồng service: không thấy -> Mono.empty()

StepVerifier.create(
        Mono.error(new IllegalStateException("downstream")))
    .expectError(IllegalStateException.class)
    .verify();
~~~

Ở đây Mock service chỉ minh họa tín hiệu; **không khẳng định** DB down sẽ thực sự phát đúng exception nếu chưa có repository test. Với **retryWhen/backoff/delay**, dùng **StepVerifier.withVirtualTime** và scheduler phù hợp để tránh test dùng Thread.sleep kéo dài hoặc không ổn định. Với test timeout sau khi headers đã gửi, cần HTTP server thật hoặc fault injection ở tầng network.

## 7. Bảo mật: kiểm 401/403, tenant và CSRF ở đúng stack

Với API dùng **OAuth2 bearer JWT**, cần kiểm ít nhất ba lớp: token có hợp lệ không, scope có cho phép thao tác không, và principal có quyền trên **order cụ thể** không.

| Tình huống | MockMvc Servlet | WebTestClient WebFlux |
|---|---|---|
| Test principal hợp lệ giả lập | **with(jwt())** | **mutateWith(mockJwt())** khi bind mock server |
| Thiếu bearer | GET không gắn jwt() → **401** | GET không mutateWith() → **401** |
| JWT có scope sai | authorities không có SCOPE_orders.read → **403** | mockJwt có authority sai → **403** |
| Tenant khác, scope vẫn đúng | Service query/DB fixtures phải từ chối | Reactive service/repository phải từ chối |
| JWT sai chữ ký/issuer/audience | Test decoder thực/real server | Test decoder thực/real server |
| Cookie/session POST | Có thể cần **with(csrf())** | Có thể cần mock CSRF token/config riêng |
| Method security | @EnableMethodSecurity + proxy phù hợp | @EnableReactiveMethodSecurity + reactive context |

Để kiểm thứ tự filter, một test HTTP nên chứng minh **401/403 không gọi service** khi user chưa đủ quyền. Chỉ assert HTTP 403 không đủ nếu implementation đã gọi database và lộ data qua log hoặc side effect trước khi từ chối.

**Cẩn trọng với 404 để che resource:** Controller thử ID thuộc tenant khác và nhận empty/404 là đúng biểu hiện, nhưng **chưa chứng minh** DB predicate đã bảo vệ. Dùng Testcontainers/DB với bản ghi A/B; caller A chỉ thấy A. Với danh sách có phân trang, phải lọc ACL **trước LIMIT/cursor**, không lấy trang của tất cả tenants rồi lọc tại Java.

### 7.1. Test CORS khác với test authentication

Với frontend browser ở origin khác, REST server có thể cần xử lý preflight OPTIONS **trước** bearer authentication:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type,idempotency-key
~~~

Kiểm response có **Access-Control-Allow-Origin/Methods/Headers** tương ứng; response của actual POST/401/403 cũng có CORS headers cho origin allowlisted khi contract yêu cầu. **CORS không xác thực token hoặc ngăn CSRF.** MockMvc có thể kiểm server headers, nhưng để chứng minh JavaScript thực sự được đọc response cần browser integration test; native WebTestClient/curl không cưỡng chế SOP.

## 8. Một bộ HTTP contract tests dùng chung cho MVC và WebFlux

MockMvc và WebTestClient dùng cách khởi tạo khác nhau nhưng API cùng public contract nên có thể **dùng chung ma trận kiểm thử**:

| Request | Kết quả yêu cầu | Vì sao |
|---|---|---|
| GET đơn tồn tại cùng tenant | 200 + JSON id/status/amount | Read representation |
| GET đơn không tồn tại | 404 Problem Details | Empty ≠ server error |
| GET đơn tenant khác | 404/403 theo policy | Chống BOLA |
| POST đúng JSON | 201 + Location + body | Create semantics |
| POST quantity=0 | 400 + invalid field path | Bean Validation cascade |
| POST sai Content-Type | 415 | HTTP media type contract |
| POST thiếu Idempotency-Key khi required | 400 | Header binding/contract |
| Retry POST cùng key/payload | Một order/outcome | Chống side effect trùng |
| Key cũ + payload khác | 409 | Fingerprint conflict |
| GET với If-None-Match khớp và còn quyền | 304 không body | Conditional request |
| PATCH với If-Match cũ | 412, không cập nhật | Optimistic concurrency |
| GET list empty | 200, items=[] | Collection semantics |
| GET list limit/cursor sai | 400 | Pagination contract |
| Hết quota | 429 + Retry-After nếu được công bố | Rate-limit behavior |
| Dependency outage | 5xx, không lộ stack trace | Resilience/error contract |

### 8.1. Chạy cùng kịch bản qua HTTP thật

**WebTestClient.bindToServer()** có thể gọi **bất kỳ HTTP server** nào, kể cả ứng dụng Spring MVC. Nhờ đó một nhóm black-box tests có thể chạy với **base URL của MVC server** và **base URL của WebFlux server**, dù unit/slice test của từng stack khác nhau.

~~~java
void verifyOrderReadable(String baseUrl, String realTestToken) {
    WebTestClient remote = WebTestClient.bindToServer()
        .baseUrl(baseUrl)
        .responseTimeout(Duration.ofSeconds(5))
        .build();

    remote.get()
        .uri("/api/orders/ord-17")
        .headers(h -> h.setBearerAuth(realTestToken))
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo("ord-17");
}
~~~

Phương thức trên cần import các Java/Spring types; **realTestToken** là token fixture hợp lệ do test identity provider phát, không phải sản phẩm của **mockJwt()**. Với **bindToServer**, không dùng mockJwt() làm cơ chế tạo authenticated request: nó chỉ hoạt động qua mock server binding/security test configurer. Test phải khởi tạo **cùng dữ liệu/expectations** độc lập ở mỗi server, nhưng không cần order ID tự nhiên trùng nếu fixture tạo khác: khi đó truyền ID thực vào test.

Test contract nên so **status, header, JSON schema, lỗi ổn định và business effects**, không ép hai implementation JSON có cùng thứ tự field, Date header hoặc server-specific error text. Việc sinh OpenAPI từ annotation không thay thế kiểm tra: gateway/proxy có thể đổi status/header mà test controller không thấy.

## 9. Những ca lỗi chỉ mock controller là chưa đủ

### 9.1. WebClient/RestClient gọi downstream: giả lập HTTP server thật

Khi service gọi payment/inventory API, mock thẳng Java interface không chứng minh HTTP client xử lý **timeout, 429/503, Retry-After, headers, JSON malformed** hoặc connection reset đúng.

Có thể dùng **WireMock, OkHttp MockWebServer** hoặc một HTTP test server tương đương. Ví dụ fragment với MockWebServer:

~~~java
mockServer.enqueue(new MockResponse()
    .setResponseCode(503)
    .addHeader("Retry-After", "2")
    .addHeader("Content-Type", "application/problem+json")
    .setBody("""
        {"type":"about:blank","title":"Unavailable","status":503}
        """));

// Gửi qua RestClient/WebClient cấu hình baseUrl tới mockServer.
// Assert response được map thành lỗi dependency thích hợp,
// không bị che thành 404 hoặc retry POST vô hạn.
RecordedRequest received = mockServer.takeRequest();
assertEquals("/inventory/BOOK-01", received.getPath());
~~~

Đây là **test fragment**, cần client fixture, method call, imports và đóng server sau test; lệnh **takeRequest()** nên có timeout để không treo mãi khi code không gửi request. Nếu API có side effect, mô phỏng mất response **sau commit**: retry cùng Idempotency-Key không tạo thêm order/charge.

### 9.2. Transaction, repository và cạnh tranh

Với GET đơn của tenant A/B, dùng DB thật hoặc Testcontainers để xác nhận query có **tenant/owner predicate**. Với POST, gửi hai request đồng thời cùng key và payload, kiểm **unique claim** và chỉ một business effect. Không kết luận an toàn idempotency chỉ vì hai lần Mockito trả cùng OrderView.

Với PATCH và **If-Match**, chạy hai updates cạnh tranh trên cùng version; chỉ một update được chấp nhận, lần còn lại nhận **412** hoặc conflict theo contract. Khi database lỗi hoặc pool cạn, kiểm **5xx/timeout**, không để handler trả empty/404 như tài nguyên không tồn tại.

### 9.3. OpenAPI contract và response errors

Ví dụ fragment OpenAPI 3.1 khai báo response GET, gồm Problem Details:

~~~yaml
paths:
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
          description: Visible order
          content:
            application/json:
              schema: {$ref: '#/components/schemas/OrderView'}
        '401': {description: Authentication required}
        '403': {description: Forbidden}
        '404':
          description: Not found or hidden
          content:
            application/problem+json:
              schema: {$ref: '#/components/schemas/ApiProblem'}
components:
  schemas:
    OrderView:
      type: object
      required: [id, status, totalAmount]
      properties:
        id: {type: string}
        status: {type: string}
        totalAmount: {type: integer, format: int64}
    ApiProblem:
      type: object
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        code: {type: string}
~~~

Đây là **fragment**, chưa có openapi/info/securitySchemes, POST schema, cache/ETag, pagination và các lỗi còn lại. Có thể dùng OpenAPI schema validator/contract test trên response thực, nhưng cần **phân biệt schema compatibility với business security**: JSON hợp schema không chứng minh order thuộc đúng tenant. Với lỗi 401/403 phát từ gateway, test phải đi qua chính tuyến gateway nếu muốn khẳng định OpenAPI mô tả response end-to-end.

## 10. Đọc kết quả test đúng, tránh kết luận quá mức

| Lỗi thiết kế test | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| MockMvc standalone trả 200 → kết luận có security | Filter chain có thể không được cài | Dùng springSecurity()/context đầy đủ; negative tests |
| Mock JWT → kết luận token chữ ký sai bị chặn | mockJwt/jwt bỏ qua decoder thật | Test decoder issuer/audience/signature/expiry riêng |
| Mockito trả empty cho tenant B → kết luận DB có ACL | Không chạy SQL thực | Integration DB test với dữ liệu A/B |
| Mock service tạo một order → kết luận POST idempotent | Không kiểm unique key/transaction | Concurrent calls + ledger/DB assertion |
| WebTestClient.expectBody() trên SSE vô hạn | Publisher không complete | returnResult + StepVerifier + cancel |
| Tất cả lỗi được map 400 | Che server bug, sai contract | Classify binding/domain/dependency/auth |
| Chỉ so status 200 | Bỏ lọt JSON/ETag/Location/cache/PII | Assert headers/schema/business effects |
| Test cố định Thread.sleep nhiều giây | Chậm, flaky, dễ race | Fake Clock, virtual time, bounded timeouts |
| Chạy slice test → kết luận reverse proxy/CORS đúng | Không đi qua gateway/socket | Real-server/browser/E2E tests |
| Chạy cả MVC và WebFlux controllers trên cùng route | Mapping trùng, kết quả khó dự đoán | Tách ứng dụng/test contexts và dùng chung contract |

**Quy tắc dữ liệu kiểm thử:** không dùng access token hoặc thông tin khách hàng production; làm sạch DB/Redis/queue theo từng test, tạo IDs khác nhau hoặc transaction rollback thích hợp. Với test bất đồng bộ, rollback trên thread test **không nhất thiết** rollback transaction của server chạy trên thread khác qua HTTP thật; cần cleanup rõ ràng.

## 11. Bài tập thực hành

**Bài 1 — Chọn công cụ.** Một API dùng Spring MVC Servlet, cần test nhanh validation và advice không mở cổng mạng. **Đáp án:** MockMvc với @WebMvcTest, import advice/security cần thiết; nếu cần toàn context/filter chain thì @SpringBootTest + @AutoConfigureMockMvc.

**Bài 2 — Reactive stream.** Flux trả SSE vô hạn, test WebTestClient.expectBody(String.class) bị timeout. **Đáp án:** Dùng **returnResult(ParameterizedTypeReference<ServerSentEvent<...>>)**, StepVerifier kiểm vài events và thenCancel; không chờ stream hoàn thành.

**Bài 3 — JWT giả lập.** MockMvc với with(jwt()) có scope đúng và trả 200. Có chứng minh JWT không hợp lệ về chữ ký bị từ chối không? **Đáp án:** Chưa. Test principal giả chỉ kiểm quy tắc authorization đã nạp; cần security integration test với JwtDecoder thật.

**Bài 4 — Phân biệt tín hiệu Mono.** Reactive repository Mono.empty() vì không có order, và Mono.error(...) do database down. Một onErrorResume(... -> Mono.empty()) áp cho mọi lỗi có đúng không? **Đáp án:** Sai. Empty có thể map 404; outage cần 5xx, không được làm giả tài nguyên không tồn tại.

**Bài 5 — Thiếu header HTTP.** POST tạo đơn test chỉ assert JSON trả về có id; actual response là 200, không có Location. **Đáp án:** Test phải assert **201 Created + Location**, schema và side effect; body đúng không đủ chứng minh HTTP contract.

**Bài 6 — Cross-tenant.** Mock service trả empty cho order tenant B; test 404 xanh. Đã chứng minh chống IDOR/BOLA chưa? **Đáp án:** Chưa; test repository thật với A/B và scope hợp lệ, truy cập chéo không được trả dữ liệu.

**Bài 7 — Response đã commit.** WebFlux phát một SSE event thành công rồi upstream lỗi. Test mong nhận 500 Problem Details. **Đáp án:** Không thể thay status sau commit. Kiểm kết thúc stream hoặc event lỗi có schema riêng nếu contract đã thiết kế.

**Bài 8 — Retry.** Client gặp timeout sau POST; test mock service đảm bảo retry trả cùng order ID. Đủ chứng minh không tạo đơn trùng? **Đáp án:** Không. Phải kiểm **idempotency ledger + unique claim + transaction** dưới concurrency, gồm trường hợp commit trước khi mất response.

## 12. Checklist trước khi merge

- [ ] Chọn đúng MockMvc cho Servlet MVC hoặc WebTestClient cho WebFlux/HTTP thật theo mục tiêu?
- [ ] Slice test nạp đủ controller, advice, security và codecs; không ngộ nhận có filter từ standalone?
- [ ] Test GET/POST/PATCH đúng method, URI, Content-Type, status, Location, ETag và Cache-Control?
- [ ] Validation DTO/JSON sai trả 400/415 với Problem Details/code ổn định, không gọi nghiệp vụ?
- [ ] JWT có negative cases cho thiếu token, sai scope, sai issuer/audience và tài nguyên tenant khác?
- [ ] Test 401/403 ở **security filter**, 404/409 ở **domain handler** đúng phạm vi?
- [ ] WebFlux kiểm Mono.empty/onError, streaming Flux, cancellation và response sau commit?
- [ ] Database/quota/idempotency/concurrency được test ở tầng tích hợp thay vì chỉ bằng mocks?
- [ ] CORS, gateway, real-server connection/timeout được kiểm qua môi trường phù hợp?
- [ ] OpenAPI contract/schema và fixtures ổn định, tests không phụ thuộc thời gian/ngủ ngẫu nhiên?

**Kết luận:** **MockMvc** giúp kiểm thử sâu HTTP boundary của **Spring MVC** mà không cần mở socket; **WebTestClient** làm điều tương tự cho **Spring WebFlux** và còn hỗ trợ response reactive/streaming. Cả hai chỉ phát huy giá trị khi assert **HTTP contract, quyền truy cập, lỗi và side effects**, đồng thời bổ sung real-server, DB và security integration tests cho những ranh giới mà mock request không thể chứng minh.

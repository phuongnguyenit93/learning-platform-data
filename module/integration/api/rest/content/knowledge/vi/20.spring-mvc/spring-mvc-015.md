# Filter, HandlerInterceptor và ranh giới trách nhiệm

## 1. Vì sao phải chọn đúng điểm mở rộng?

Một REST API cần request ID, đo latency, phân quyền, lỗi chuẩn và audit. Đặt tất cả vào controller gây lặp; dồn vào một Filter/Interceptor dễ sai khi không khớp route, security từ chối hoặc xử lý async.

Hai cơ chế thường bị nhầm lẫn:

- **Servlet Filter** nằm ở tầng **Servlet container**, bao quanh một servlet request/response trước cả khi Spring MVC biết controller nào sẽ được gọi.
- **HandlerInterceptor** nằm trong **Spring MVC HandlerMapping**, có thể quan sát handler đã được chọn và tham gia lifecycle trước/sau xử lý MVC.
- **Controller/service, Spring Security, Bean Validation, ControllerAdvice** có ranh giới riêng; không phải điều gì cũng nên đặt vào một trong hai loại interceptor.

Bài thuộc chương **Spring MVC**, module **INTEGRATION_API_REST**, trong bối cảnh resource, URI, HTTP methods/status, OpenAPI, security, lỗi, cache, idempotency và Java/Spring. Trọng tâm là **ranh giới lifecycle và bảo mật**.

Sau bài học, bạn có thể giải thích thứ tự filter–dispatcher–interceptor, viết ví dụ Spring Boot 3, xử lý exception/async, đo metric không lộ PII và xây test chứng minh từng nhánh hoạt động đúng.

## 2. Đường đi của một HTTP request

Với Spring MVC trên Servlet stack, luồng xử lý đồng bộ được giản lược:

~~~mermaid
flowchart TD
    A["HTTP client"] --> B["Gateway / proxy"]
    B --> C["Servlet Filter chain"]
    C --> S["Spring Security FilterChainProxy (nếu có)"]
    S --> D["DispatcherServlet"]
    D --> M["HandlerMapping chọn handler và interceptor"]
    M --> P["HandlerInterceptor.preHandle"]
    P --> H["HandlerAdapter: argument resolution, validation, controller"]
    H --> V["Service / domain / database"]
    V --> R["Return value handler / message converter"]
    R --> Q["HandlerInterceptor.postHandle (khi thích hợp)"]
    Q --> X["Render / hoàn tất MVC"]
    X --> Y["HandlerInterceptor.afterCompletion"]
    Y --> Z["Filter chain quay về client"]
~~~

Sơ đồ là **happy path đồng bộ**, không áp dụng nguyên xi cho exception/async. Spring Security nằm trong servlet filter chain; thứ tự các filter phụ thuộc cấu hình.

### 2.1. Filter bao quanh toàn servlet pipeline

~~~text
Filter A: trước
  Filter B: trước
    DispatcherServlet
  Filter B: sau
Filter A: sau
~~~

Filter có thể dừng request trước khi gọi phần tiếp theo của chain. Khi đó controller, HandlerInterceptor và các MVC exception resolver có thể không chạy. Filter được cấu hình phù hợp có thể thấy cả 401 từ security, 404 không có handler, static resources hoặc ERROR dispatch.

### 2.2. HandlerInterceptor tham gia sau khi chọn handler

~~~text
Interceptor A.preHandle
  Interceptor B.preHandle
    Controller/handler
  Interceptor B.postHandle
Interceptor A.postHandle
Interceptor B.afterCompletion
Interceptor A.afterCompletion
~~~

Trình tự trên đòi **mọi preHandle trả true** và xử lý đồng bộ. Interceptor thấy handler đã match (thường là HandlerMethod) và route pattern; Filter thông thường chưa biết handler này.

## 3. Ma trận chọn điểm mở rộng

| Nhu cầu | Nơi phù hợp | Lý do |
| --- | --- | --- |
| Gắn **X-Request-ID** cho response, kể cả lỗi chặn sớm | **Filter** đặt đúng thứ tự | Bao quanh request trước MVC. |
| MDC, trace context tại request thread | Filter + **tracing infrastructure** | Cleanup phải đúng và async cần propagation riêng. |
| Đo latency theo **route template** và HandlerMethod | **HandlerInterceptor** hoặc framework metrics | Biết handler đã map, tránh dùng path chứa ID thật. |
| Đọc annotation tùy chỉnh của controller | **HandlerInterceptor** | HandlerMethod đã có metadata. |
| Xác thực JWT/OAuth2, entry point 401/403, CSRF | **Spring Security filter chain** | Có cơ chế bảo mật, exception handlers, method security. |
| Quyền truy cập đơn hàng của tenant | **Service/domain** và method security | Phải đọc resource thật, path matching không đủ. |
| Validate JSON/DTO | **Argument resolver, Bean Validation, controller** | Cần áp ràng buộc field/schema. |
| Chuyển exception MVC thành Problem Details | **@RestControllerAdvice** | Gắn với MVC error handling. |
| Lỗi phát sinh trước DispatcherServlet | **Security handlers / chuyên biệt Filter** | MVC ControllerAdvice có thể không chạy. |
| Idempotency và race condition của POST | **Service + persistent storage nguyên tử** | Chỉ thấy header chưa chống lệnh chạy lặp. |
| Quota/rate limit phân tán | **Gateway / limiter có shared state** | Local interceptor không chia sẻ trạng thái giữa instance. |
| Audit thay đổi nghiệp vụ | **Domain/service** | Biết hành động thành công/rollback và quyền người dùng. |
| Dữ liệu response dạng streaming | **Controller/service streaming**, log metadata tại Filter | Tránh buffer file lớn hoặc thay đổi body. |

**Nguyên tắc:** Filter cho logic mức servlet; Interceptor khi cần biết handler MVC; Security, service, validator và exception handler cho trách nhiệm chuyên biệt. Không dùng “có thể đọc request” làm lý do duy nhất để đặt nghiệp vụ vào một điểm mở rộng.

## 4. Servlet Filter: ví dụ Request ID an toàn

Spring cung cấp **OncePerRequestFilter**, thuận tiện để hạn chế gọi lặp trong một dispatch. Tuy nhiên, nó **không mặc nhiên bảo đảm chạy một lần cho toàn bộ vòng đời async/error**. Dispatcher types và các hook của lớp quyết định.

### 4.1. Tạo hoặc chấp nhận X-Request-ID có giới hạn

~~~java
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public final class RequestIdFilter extends OncePerRequestFilter {
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String incoming = request.getHeader("X-Request-ID");
        String requestId = incoming != null
                && SAFE_ID.matcher(incoming).matches()
                ? incoming
                : UUID.randomUUID().toString();

        response.setHeader("X-Request-ID", requestId);
        MDC.put("requestId", requestId);
        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

**MDC phải được dọn trong finally**, kể cả khi controller ném exception, vì thread của container có thể được tái sử dụng. Whitelist ID tránh ký tự điều khiển và nhãn log không giới hạn. Đây là correlation ID, **không phải idempotency key, authentication token hoặc bằng chứng client đáng tin**. Với distributed tracing, chuẩn W3C Trace Context có ý nghĩa riêng.

### 4.2. Đăng ký filter, không đăng ký trùng

Ví dụ dùng FilterRegistrationBean; không đồng thời thêm @Component trên RequestIdFilter:

~~~java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
class RequestFilterConfig {
    @Bean
    FilterRegistrationBean<RequestIdFilter> registerRequestIdFilter() {
        var registration = new FilterRegistrationBean<RequestIdFilter>();
        registration.setFilter(new RequestIdFilter());
        registration.addUrlPatterns("/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }
}
~~~

Kiểm thử order với CORS/Security. Muốn 401/403 cũng có request ID, filter phải chạy **trước nơi security từ chối**. Gateway ID cần chính sách trust/propagation.

### 4.3. Không tự đọc body trong Filter để log

Đọc InputStream trong Filter có thể làm @RequestBody rỗng. **ContentCachingRequestWrapper** chỉ cache byte đã được đọc; cần giới hạn dung lượng và redaction. Response wrapper không được phá streaming/Content-Length. **Không log body thô chứa secrets/PII**.

## 5. HandlerInterceptor: theo dõi handler đã định tuyến

Ba callback chính:

- **preHandle(request, response, handler):** chạy trước handler; true tiếp tục, false kết thúc việc xử lý handler hiện tại.
- **postHandle(request, response, handler, modelAndView):** chạy sau handler khi luồng đồng bộ đi tới điểm thích hợp, trước view rendering. Với @ResponseBody/ResponseEntity, body có thể đã được serialize/ghi, nên đừng định sửa JSON hoặc header bắt buộc tại đây.
- **afterCompletion(request, response, handler, ex):** cleanup sau MVC cho interceptor có preHandle thành công. Tham số ex không phải sổ ghi đầy đủ các lỗi đã được HandlerExceptionResolver xử lý.

### 5.1. Đo thời lượng handler với route pattern

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.HandlerMapping;

@Component
public final class HandlerTimingInterceptor implements HandlerInterceptor {
    private static final Logger LOG =
            LoggerFactory.getLogger(HandlerTimingInterceptor.class);
    private static final String START =
            HandlerTimingInterceptor.class.getName() + ".start";

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        if (request.getAttribute(START) == null) {
            request.setAttribute(START, System.nanoTime());
        }
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {
        Object started = request.getAttribute(START);
        if (!(started instanceof Long start)) {
            return;
        }
        request.removeAttribute(START);
        Object matched =
                request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
        String route = matched instanceof String
                ? (String) matched : "unmatched";
        long elapsedMs = (System.nanoTime() - start) / 1_000_000L;
        LOG.info("method={} route={} status={} elapsedMs={}",
                request.getMethod(), route, response.getStatus(), elapsedMs);
    }
}
~~~

Log **route template**, không log UUID thật. Thời lượng interceptor không bao gồm mọi filter/gateway/network.

### 5.2. Đăng ký theo nhóm route

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class MvcObservabilityConfig implements WebMvcConfigurer {
    private final HandlerTimingInterceptor timing;
    MvcObservabilityConfig(HandlerTimingInterceptor timing) {
        this.timing = timing;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(timing).addPathPatterns("/api/**");
    }
}
~~~

Kiểm tra context path, actuator và handler mappings khác. **Path pattern không phải ranh giới bảo mật**.

### 5.3. preHandle trả false có hệ quả gì?

Nếu preHandle trả false, handler không chạy. Interceptor từ chối phải **tự thiết lập status/body** hoặc delegate cho cơ chế lỗi phù hợp. Nó không nhận afterCompletion cho chính mình khi preHandle chưa thành công; các interceptor trước nó đã chạy thành công có thể được callback cleanup. Trả false mà không set response dễ tạo **200 rỗng**, rất khó phát hiện.

Với lỗi nghiệp vụ và validation, nên để controller/service báo lỗi và @RestControllerAdvice biến thành Problem Details thay vì viết JSON lỗi thủ công trong nhiều interceptor.

## 6. Exception, async và dispatch: khác happy path ra sao?

| Tình huống | Filter | HandlerInterceptor | Điểm dễ sai |
| --- | --- | --- | --- |
| Controller thành công đồng bộ | Chạy trước/sau chain. | preHandle → handler → postHandle → afterCompletion. | Latency hai lớp khác nhau. |
| Security trả 401/403 trước MVC | Filter đứng trước security có thể quan sát. | Có thể **không chạy**. | Không dùng interceptor thay authentication entry point. |
| Không có handler / 404 | Filter thường có thể chạy. | Không bảo đảm chọn được handler/controller. | Còn tùy resource mapping/error dispatch. |
| Controller ném exception | Finally của filter vẫn chạy nếu stack quay về. | postHandle có thể bỏ, afterCompletion cho interceptor đủ điều kiện. | Resolver có thể đã xử lý lỗi, tham số ex không đầy đủ. |
| preHandle trả false | Filter vẫn quay về. | Không gọi controller; callback khác happy path. | Phải set status/body đúng. |
| Callable/DeferredResult/async | Có thể nhiều servlet dispatch. | Có thể có callback khi kết quả được dispatch tiếp. | Thread mới không tự có MDC. |
| ERROR dispatch | Tùy filter registration. | Tùy HandlerMapping. | Không kỳ vọng một hook bắt hết lỗi container. |

### 6.1. OncePerRequestFilter không phải once-per-request-lifetime

Servlet có **DispatcherType.REQUEST, ASYNC, ERROR**. OncePerRequestFilter có các hook **shouldNotFilterAsyncDispatch()**, **shouldNotFilterErrorDispatch()** và cơ chế đánh dấu đã lọc trong một dispatch. Dispatcher type thực sự áp dụng còn phụ thuộc filter registration.

MDC chỉ tồn tại trên **thread hiện tại**. Callable/@Async cần **context propagation** và cleanup riêng; request attribute không tự truyền ThreadLocal.

### 6.2. AsyncHandlerInterceptor

Khi handler bắt đầu async, Spring MVC có thể gọi **AsyncHandlerInterceptor.afterConcurrentHandlingStarted(...)** thay vì postHandle/afterCompletion ở initial dispatch, rồi xử lý tiếp khi có result dispatch.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.AsyncHandlerInterceptor;

public final class AsyncLifecycleInterceptor
        implements AsyncHandlerInterceptor {
    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        // Initial dispatch kết thúc để chuyển sang async.
        // Không coi đây là lúc HTTP request đã hoàn tất.
    }
}
~~~

Timing interceptor giữ start qua resumed dispatch; timeout/cancel cần xử lý riêng. Ưu tiên instrumentation async của Spring/Micrometer/OpenTelemetry cho latency end-to-end.

### 6.3. postHandle không phải nơi sửa JSON

Với @ResponseBody/ResponseEntity, response converter có thể đã ghi hoặc commit body khi postHandle chạy. Đừng thêm field JSON, sửa Content-Type/ETag hay đổi status sau cùng ở đây. Dùng **controller/ResponseEntity** cho contract, hoặc response advice đúng chức năng có test.

### 6.4. Exception ngoài DispatcherServlet

Lỗi auth trong security chain, HTTP parsing ở container, CORS preflight và gateway rejection có thể xảy ra **trước MVC exception resolver**. @RestControllerAdvice không tự bắt các lỗi này. Muốn trả Problem Details đồng nhất, cần security handlers và error writer ở filter/gateway theo cùng hợp đồng.

## 7. Bảo mật thuộc Security và domain, không thuộc timing interceptor

Không viết interceptor kiểu “nếu path bắt đầu /admin thì kiểm tra role” làm bảo vệ chính. Route mới, alternate handler mappings hoặc request bên ngoài MVC có thể bypass; interceptor cũng không xử lý đầy đủ token, session, CSRF và quyền sở hữu dữ liệu.

### 7.1. Ví dụ Spring Security cho route

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(
                    Customizer.withDefaults()))
            .build();
    }
}
~~~

Đoạn này giả định OAuth2 Resource Server với JWT issuer/JWK đã cấu hình. Cần cấu hình **CORS, CSRF** theo client thật: API dùng Bearer header khác ứng dụng đăng nhập cookie/session, nơi CSRF protection có thể cần thiết. Không tắt CSRF toàn cục chỉ vì tên endpoint là REST.

Security rule kiểm tra quyền cấp thao tác; service vẫn phải xác minh actor/tenant đối với từng order:

~~~java
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

record OrderView(UUID id, String status, long totalMinorUnit) {}
interface OrderQueryService {
    OrderView findAuthorized(String actor, UUID orderId);
}

@RestController
@RequestMapping("/api/orders")
class OrdersController {
    private final OrderQueryService service;
    OrdersController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(
            @PathVariable UUID id, Authentication auth) {
        return ResponseEntity.ok(
                service.findAuthorized(auth.getName(), id));
    }
}
~~~

**findAuthorized** phải được triển khai kiểm tra resource/tenant thật. Không lấy tenant từ query do client tùy ý chọn. Có thể thêm @EnableMethodSecurity và @PreAuthorize cho các quy tắc thích hợp, nhưng quyền sở hữu object vẫn phải được áp trong domain/service.

### 7.2. Phân loại lỗi HTTP

| Tình huống | Status | Lớp xử lý |
| --- | --- | --- |
| Thiếu hoặc sai Bearer token | **401** với WWW-Authenticate phù hợp | Security authentication entry point. |
| Đã xác thực nhưng thiếu scope | **403** | Security access denied handler. |
| Biết ID nhưng không có quyền sở hữu | **403** hoặc **404** theo chính sách che tồn tại | Service authorization + exception mapping. |
| Resource theo ID không tồn tại | **404** | Service + MVC exception handler. |
| Body JSON/validation sai | **400/422** theo contract | MVC argument validation + handler. |
| Lỗi không mong đợi | **5xx** với nội dung an toàn | MVC/security/gateway error pipeline phù hợp. |

Request ID trong response giúp tra log nhưng không cấp quyền. Không để Filter tự biến 401 thành 200 hoặc log access token.

## 8. Error handling: ControllerAdvice dành cho lỗi MVC

~~~java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

class OrderNotFoundException extends RuntimeException {}

@RestControllerAdvice
class OrdersProblemHandler {
    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound() {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Không tìm thấy đơn hàng.");
        problem.setTitle("Order not found");
        problem.setType(URI.create(
                "https://api.example.com/problems/order-not-found"));
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

@RestControllerAdvice dùng cho exception xảy ra trong pipeline MVC; security 401/403 trước MVC phải được xử lý bởi Spring Security handlers. Đừng cố gọi ControllerAdvice như một helper từ Filter, hoặc dựa hoàn toàn vào đối số exception ở afterCompletion: exception có thể đã được MVC resolver xử lý. Với thông tin nhạy cảm, body lỗi cần redaction, type/code ổn định và không lộ stack trace.

## 9. Quan sát vận hành và contract HTTP

### 9.1. Correlation, tracing và latency không đồng nghĩa

- **X-Request-ID:** định danh liên kết log theo request; xác định whitelist và trust boundary.
- **traceparent/span:** tracing phân tán theo W3C và OpenTelemetry/Micrometer, có context và sampling riêng.
- **HTTP server latency:** thời gian toàn request tại server; **handler latency:** phạm vi MVC; **DB latency:** tầng truy vấn.

Đừng gọi metric trong interceptor là request-total-time rồi tuyên bố nó bao gồm gateway, security, network và async queue. Khi dùng async, initial dispatch có thể kết thúc rất sớm so với response thật.

### 9.2. Labels và dữ liệu cá nhân

Nhãn tốt: method, **route template**, status family. Tránh UUID/email/token/query/body. Audit chính thức ghi **sự kiện nghiệp vụ đã commit** ở service với redaction/retention.

### 9.3. Những hành vi thuộc controller/service

**ETag, Cache-Control, Location, Content-Type, 201/202/204, idempotency và transaction** phụ thuộc resource/nghiệp vụ. Filter có thể thêm header kỹ thuật chung, nhưng không nên đổi status hoặc tự đoán đơn đã được tạo. Interceptor thời gian không biết service đã commit, rollback hay tạo side effect, nên không thay thế domain audit.

## 10. Kiểm thử thực tế: success, failure và async

### 10.1. Ma trận kiểm thử

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| F01 | GET hợp lệ | Filter gắn X-Request-ID, interceptor đo route, body/status đúng. |
| F02 | GET không token | Security trả 401, Filter trước security vẫn gắn request ID; service không gọi. |
| F03 | Token thiếu scope | 403; không vào service. |
| F04 | Token có scope nhưng order khác tenant | Service từ chối 403/404 theo policy. |
| F05 | Controller ném OrderNotFoundException | ControllerAdvice trả 404 Problem Details; MDC được cleanup. |
| F06 | URL không tồn tại | 404; Filter có thể chạy nhưng interceptor controller không được bảo đảm. |
| F07 | Interceptor preHandle trả false | Handler không chạy; status/body và cleanup đúng. |
| F08 | JSON sai/validation fail | 400/422 theo contract, không log body nhạy cảm. |
| F09 | Callable/DeferredResult | Không đếm metric đôi; async context và timeout được xử lý. |
| F10 | 401/5xx qua gateway | X-Request-ID an toàn, không chèn header hoặc lộ token. |
| F11 | Client gửi ID chứa CR/LF hoặc quá dài | Filter tạo UUID mới. |
| F12 | Body lớn/streaming | Không tự buffer toàn dữ liệu hoặc phá luồng stream. |

### 10.2. MockMvc có Security và Filter

Ví dụ test tích hợp trong một context Spring Boot có RequestIdFilter và SecurityFilterChain đã trình bày:

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RequestPipelineIT {
    @Autowired MockMvc mvc;
    private static final UUID ORDER_ID = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");

    @Test
    void authorizedRequestHasRequestId() throws Exception {
        mvc.perform(get("/api/orders/{id}", ORDER_ID)
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")))
                .header("X-Request-ID", "test_req_001"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Request-ID", "test_req_001"));
    }

    @Test
    void unauthorizedRequestAlsoHasRequestId() throws Exception {
        mvc.perform(get("/api/orders/{id}", ORDER_ID))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("X-Request-ID"));
    }
}
~~~

**Điều kiện chạy:** cần dependency **spring-security-test**, fixture/mock OrderQueryService trả OrderView cho ID khi được phép và security context/JWT test thích hợp. Test trên chưa chứng minh giao dịch DB hay quyền tenant. Bổ sung test JWT thiếu authority để kiểm 403; nếu tắt security ở test, không thể suy ra quy tắc bảo mật của production.

### 10.3. Kiểm tra thứ tự callback

Với interceptor test thu thập sự kiện trong một collector thread-safe:

~~~text
GET /api/orders/123 (success, sync)
expected: filter.before, interceptor.pre, controller,
          interceptor.post (nếu có), interceptor.after, filter.after

GET /api/orders/123 (security rejects)
expected: filter.before, security.reject, filter.after
not expected: interceptor.pre, controller
~~~

Timing interceptor ở phần 5 không override postHandle nên cần collector khác nếu muốn test callback ấy. Với async, thử MockMvc **asyncStarted → asyncDispatch**, timeout và context propagation, bảo đảm không ghi hai metric cho một HTTP request.

**Không chỉ test happy path:** lỗi phổ biến là Filter có ID trên 200 nhưng không có trên 401, callback afterCompletion không chạy khi preHandle false, hoặc MDC rò sang request kế tiếp.

## 11. Các phản mẫu thường gặp

| Phản mẫu | Tại sao sai? | Thiết kế đúng hơn |
| --- | --- | --- |
| HandlerInterceptor thay Spring Security | Handler mapping không bảo vệ mọi đường vào. | SecurityFilterChain + domain auth. |
| Filter đọc raw body để log | Tiêu thụ stream, lộ PII, tăng RAM. | Metadata và redaction có giới hạn. |
| preHandle false nhưng không set status | Client nhận 200 rỗng. | Trả status/body hợp đồng hoặc lỗi thích hợp. |
| Mỗi filter/interceptor tự phát JSON lỗi | Response không nhất quán. | Schema Problem Details, xử lý ở đúng lớp. |
| Thêm ETag/Location trong postHandle | Response có thể đã commit. | ResponseEntity/controller/service. |
| Dùng URL có UUID làm metric label | Cardinality cao, lộ dữ liệu. | Route template. |
| Đặt MDC nhưng không dùng finally | Rò context qua thread reuse. | Cleanup và async context propagation. |
| Tin OncePerRequestFilter chạy duy nhất trên mọi dispatch | Sai với REQUEST/ASYNC/ERROR. | Kiểm tra hook và dispatcher types. |
| Rate limiter bằng counter trong interceptor | Không đồng bộ giữa nhiều instance. | Shared-state limiter/gateway. |
| Audit “order created” trước handler | Transaction có thể rollback. | Domain audit sau commit/outbox. |

## 12. Bài tập: phân chia trách nhiệm cho Orders API

Một ứng dụng Spring Boot có **GET /api/orders/{id}**, **POST /api/orders**, **GET /public/health** và **GET /api/reports/{id}/download**. Dùng JWT Bearer, proxy và endpoint bất đồng bộ. Yêu cầu mọi response có request ID, đo p95 theo route, không log bí mật, trả lỗi chuẩn, tenant chỉ đọc đơn của mình và download không bị buffer.

**Yêu cầu:** (1) Chọn nơi đặt request ID, timing, auth, tenant check và error mapping. (2) Mô tả đường đi khi thiếu JWT và khi controller ném exception. (3) Chỉ ra cách xử lý MDC/metric với Callable. (4) Đề xuất ba phép thử xác minh 401 có ID, quyền tenant và streaming. (5) Nêu chính sách CORS/preflight phù hợp.

**Hướng giải:** Filter trước security tạo ID; Spring Security kiểm Bearer/scope và CORS; service kiểm tenant; ControllerAdvice xử lý lỗi MVC, security handlers xử lý 401/403; timing theo route ở interceptor hoặc framework observations. Với async, dùng context propagation và callback đúng, không lấy thời gian initial dispatch làm toàn bộ latency. Test 401 còn X-Request-ID, tenant khác bị từ chối, và download stream không bị đọc vào RAM; CORS phải giới hạn origin/credentials và xử lý preflight trước khi auth chặn nhầm.

## 13. Checklist triển khai

- [ ] Phân biệt **Filter ở Servlet layer** với **HandlerInterceptor ở MVC layer**.
- [ ] Kiểm tra Filter order, URL pattern, dispatcher types và Spring Security chain trong context thật.
- [ ] Request ID hợp lệ, không log secrets; MDC cleanup trong finally.
- [ ] Interceptor đo theo route template, hiểu preHandle/postHandle/afterCompletion.
- [ ] preHandle false không tạo 200 rỗng; cleanup interceptor trước đó đúng.
- [ ] Async, ERROR dispatch, timeout và thread context được test; không mặc định once-per-lifetime.
- [ ] Authentication/authorization thuộc Security và service/domain, không trông chờ interceptor.
- [ ] Lỗi MVC dùng ControllerAdvice/ProblemDetail, lỗi security xử lý ở security layer.
- [ ] ETag, Location, cache, idempotency, transaction và audit thuộc đúng tầng nghiệp vụ.
- [ ] MockMvc/integration tests bao phủ 200, 401, 403, 404, exception, async và streaming.

**Kết luận:** Filter bao quanh Servlet request; HandlerInterceptor tham gia vòng đời handler được Spring MVC lựa chọn. Chúng bổ sung cho nhau nhưng **không thay thế Spring Security, validation, ControllerAdvice hoặc service**. Khi ranh giới rõ, thứ tự và async được kiểm thử, REST API vừa quan sát được vừa giữ đúng hợp đồng bảo mật và dữ liệu.

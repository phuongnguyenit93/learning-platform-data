# Spring MVC — Chọn đúng điểm mở rộng cho ghi log, đo thời gian và truyền mã đối chiếu

## 1. Mục tiêu

Một ứng dụng Spring MVC cần quan sát request: ai gọi endpoint nào, có lỗi không, mất bao lâu, và log nào thuộc cùng một request. Nhưng **ghi log**, **đo thời gian** và **truyền mã đối chiếu** không nhất thiết nằm cùng một điểm mở rộng.

Nếu đặt mọi logic vào `HandlerInterceptor`, bạn có thể bỏ sót request bị từ chối trước khi tới controller. Nếu đặt mọi logic vào Servlet `Filter`, bạn chưa chắc biết **route template** như `/api/orders/{id}`, hoặc đo nhầm thời gian của một request bất đồng bộ. Nếu tự ghi timer và trace cho mọi request trong khi Spring Boot/Micrometer đã có instrumentation, bạn có thể tạo metrics trùng và log khó đối chiếu.

Sau bài học, bạn có thể:

- Phân biệt **Servlet Filter / OncePerRequestFilter**, **HandlerInterceptor / AsyncHandlerInterceptor**, **@ControllerAdvice / ResponseBodyAdvice**, và **Micrometer Observation/Tracing**.
- Chọn đúng tầng cho **request ID**, **MDC**, **access log**, **handler timing**, **HTTP metrics**, **tracing**, bảo mật và response customization.
- Giải thích thứ tự gọi filter → DispatcherServlet → HandlerMapping/interceptor → controller → render/serialize → filter, và vòng đời khi có async/error dispatch.
- Tạo mã đối chiếu `X-Request-ID` an toàn, dùng chung giữa response header, request attributes, MDC và application logs; không tin vô điều kiện ID do client cung cấp.
- Đo thời gian bằng `System.nanoTime()`, phân biệt thời gian **filter dispatch**, **handler**, **HTTP request tổng thể**, và thời gian service/downstream.
- Tránh rò dữ liệu khi log headers/query/body; hiểu caching wrappers và giới hạn logging request/response payload.
- Viết ví dụ runnable bằng **Java 17+, Spring Boot 3.5.0 / Spring Framework 6.2**, kèm MockMvc tests.

Bối cảnh là **Spring Web MVC trên Servlet stack**, không phải WebFlux. Ví dụ có minh họa các công cụ quan sát phổ biến và một ứng dụng nhỏ có thể chạy; các fragment riêng lẻ được ghi chú khi chưa phải class hoàn chỉnh.

## 2. Bảng chọn điểm mở rộng theo mục tiêu

| Việc cần làm | Điểm mở rộng nên cân nhắc | Vì sao | Lưu ý |
| --- | --- | --- | --- |
| Sinh/kiểm tra mã đối chiếu từ đầu request, gắn header response | Servlet `Filter` / `OncePerRequestFilter`, hoặc trusted gateway | Chạy trước DispatcherServlet/handler; bao phủ cả request chưa tới controller | Phải xử lý filter ordering, ASYNC/ERROR dispatch, cleanup MDC |
| Thêm request ID vào log hiện tại | Servlet Filter + SLF4J `MDC` | Cần đặt sớm và xóa chắc chắn trong `finally` | MDC thường dựa vào ThreadLocal, không tự qua worker mới |
| Log method/status/thời gian ở ranh giới Servlet | Filter hoặc container access log | Biết request/response, kể cả lỗi trước MVC | Với async, `chain.doFilter` kết thúc sớm, không đồng nghĩa HTTP response đã xong |
| Log tên handler và URI **template** | `HandlerInterceptor` | Được chạy sau handler mapping, biết route/handler | Không bao phủ mọi thứ trước mapping/filter |
| Đo thời gian riêng một handler MVC | `HandlerInterceptor` + `System.nanoTime()` | Có `preHandle`, `afterCompletion`, route pattern | Cần xét `AsyncHandlerInterceptor` và async lifecycle |
| Đo latency HTTP, số lần gọi, phân nhóm status, traces | **Spring Boot Actuator + Micrometer Observation/Tracing** | Có instrumentation và conventions sẵn | Không tự thêm timer trùng; kiểm soát tag cardinality |
| Đo một bước nghiệp vụ/service | `ObservationRegistry`, `Timer` hoặc instrumentation cho service | Phản ánh thời gian DB/business, không phải toàn HTTP | Chọn tên/tag ít biến thể và scope phù hợp |
| Sửa body JSON kết quả controller | `ResponseBodyAdvice` hoặc HTTP message converter | Có thể can thiệp trước serialize response của MVC | Không áp dụng cho mọi lỗi từ filter, file/stream/proxy |
| Chuẩn hóa HTTP exception response | `@RestControllerAdvice` / `@ExceptionHandler` / `ResponseEntityExceptionHandler` | Phân loại lỗi ở web MVC | Không thay thế security filter exception handling |
| Authentication/authorization, CORS, một số security headers | **Spring Security filter chain** và cấu hình security | Bảo vệ sớm, bao phủ trước controller | Không dùng interceptor làm lớp security chính |
| Access log do reverse proxy / servlet container tạo | Proxy access log / container valve | Quan sát kể cả khi Spring app không xử lý được | Dữ liệu header/query phải được redact phù hợp |

**Quy tắc thực hành:** dùng ít công cụ nhất nhưng bao phủ **đúng ranh giới**. Đặt ID ở filter/gateway, handler-aware logs ở interceptor nếu thực sự cần, HTTP metrics/traces ở Micrometer, nghiệp vụ tại service, lỗi ở advice. Không dùng `@ControllerAdvice` để đo request end-to-end hoặc MVC interceptor như một giải pháp security toàn diện.

## 3. Thứ tự các giai đoạn của request

### 3.1. Request đồng bộ

~~~text
Client → Servlet container → Filter A (Request-ID/MDC)
       → Spring Security filter chain (nếu có)
       → DispatcherServlet / HandlerMapping
       → HandlerInterceptor.preHandle
       → HandlerAdapter gọi Controller method
       → HandlerAdapter xử lý return value
          ├─ REST @ResponseBody: HttpMessageConverter ghi body,
          │  response CÓ THỂ đã commit
          └─ View: tạo ModelAndView, CHƯA render
       → HandlerInterceptor.postHandle (khi handler thành công)
       → Render view nếu có
       → HandlerInterceptor.afterCompletion
       → Filter A finally (đo dispatch, dọn MDC)
       → HTTP response
~~~

Đây là **luồng đồng bộ giản lược**, không mô tả mọi exception/forward/async case. Thứ tự filter phụ thuộc registration. Điểm chính cần nhớ: khi `@ResponseBody` hoặc `ResponseEntity` được return-value handler xử lý, JSON có thể **đã được serialize/commit trước `postHandle`**; còn với MVC view thông thường, `postHandle` chạy **trước** view rendering. Vì vậy không đặt header quan trọng ở `postHandle` và kỳ vọng luôn được gửi; chọn Filter ở thời điểm sớm, controller/`ResponseEntity` hoặc `ResponseBodyAdvice` tùy phạm vi.

### 3.2. Filter nằm ngoài MVC

Servlet filter là API của Jakarta Servlet:

~~~java
void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain) throws IOException, ServletException;
~~~

Vì filter đứng trong container chain, nó có thể thực hiện công việc trước/sau `chain.doFilter(...)` mà không cần biết controller. Nó vẫn chạy với những request không được MVC map thành handler, tùy URL patterns và dispatcher types đã đăng ký.

**Điểm mạnh:** logging bắt đầu sớm, request ID, header, wrapper/body policy, security integration. **Giới hạn:** có thể chưa biết chính xác route template; trạng thái HTTP và body có thể chưa hoàn tất ở thời điểm filter kết thúc trong async requests.

### 3.3. Interceptor nằm trong MVC

`HandlerInterceptor` được `HandlerMapping` áp dụng cho một handler phù hợp:

~~~java
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) throws Exception;

public void postHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        ModelAndView modelAndView) throws Exception;

public void afterCompletion(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex) throws Exception;
~~~

- `preHandle` trước handler, trả `false` để ngừng handler chain.
- `postHandle` sau xử lý handler đồng bộ, nhưng có thể đã quá muộn để sửa body/header (đặc biệt response JSON).
- `afterCompletion` sau khi MVC hoàn thành request trong trường hợp thông thường, phù hợp cleanup/timing/logging; `ex` không phải lúc nào cũng chứa lỗi thực tế nếu exception đã được resolver xử lý.
- `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` có thể cung cấp route template như `/api/orders/{id}` sau mapping, hữu ích cho log/metrics ít cardinality.

Interceptor không phải thay thế cho Spring Security: một số request hoặc URL matching/filter paths không qua cùng interceptor chain. Tránh dùng nó để tạo lớp bảo vệ authentication/authorization duy nhất.

## 4. Mã đối chiếu: requestId, traceId và error code

| Tên | Ví dụ | Vai trò |
| --- | --- | --- |
| `X-Request-ID` / `requestId` | `2f7c7b2b-f418-4297-b042-c86f86e76053` | Đối chiếu một request giữa response và log |
| Distributed `traceId` | ID theo W3C trace context | Liên kết nhiều spans qua các service |
| `spanId` | Một span trong trace | Phân biệt từng operation |
| Public error code | `ORDER_NOT_FOUND` | Cho client biết loại lỗi, ổn định qua nhiều requests |
| HTTP status | 400, 404, 409, 500 | Diễn tả kết quả theo HTTP semantics |

**Request ID không phải error code.** Cùng một `ORDER_NOT_FOUND` xuất hiện ở nhiều request có các request IDs khác nhau. Nếu hệ thống đã dùng Micrometer Tracing/OpenTelemetry, không tự suy ra `traceId == requestId`; một trace có thể chứa nhiều requests qua nhiều services.

### 4.1. Sinh ID an toàn

Ví dụ cho ứng dụng độc lập:

~~~java
String requestId = UUID.randomUUID().toString();
request.setAttribute("requestId", requestId);
response.setHeader("X-Request-ID", requestId);
~~~

Lưu ID trong request attribute giúp các thành phần ở **cùng HTTP request** truy cập nó mà không chỉ phụ thuộc vào MDC. Đặt header trước khi response có thể bị commit; đừng đợi `afterCompletion` mới thêm header.

Không trực tiếp tin `X-Request-ID` từ bất kỳ client nào. Header do client gửi có thể:

- Quá dài, chứa ký tự không phù hợp/log-injection.
- Trùng ID của người khác, gây spoofing và khó đối chiếu.
- Mang dữ liệu nhạy cảm trong chính giá trị header.

**Chính sách đơn giản:** luôn sinh ID ở server, không sử dụng giá trị client. Trong hệ thống có **trusted gateway**, có thể cho phép gateway cấp ID và backend kiểm tra độ dài, charset, nguồn trust/forwarded headers. Tránh tự tạo thêm một request ID mỗi tầng nếu bạn đang chủ ý theo dõi cùng một edge request.

### 4.2. MDC cho log

SLF4J MDC lưu context theo thread của logging backend (thường ThreadLocal):

~~~java
String previous = MDC.get("requestId");
MDC.put("requestId", requestId);
try {
    chain.doFilter(request, response);
} finally {
    if (previous == null) MDC.remove("requestId");
    else MDC.put("requestId", previous);
}
~~~

Restore giá trị cũ giúp an toàn khi có scope lồng nhau. Không đặt token, password, cookie, email nhạy cảm vào MDC vì phần lớn log appenders có thể in mọi MDC keys. MDC trong servlet thread **không tự propagate** sang `@Async`, `CompletableFuture`, scheduled job hay thread pool khác.

### 4.3. Async context propagation

Nếu cần request ID trong `@Async`, bạn có thể:

- Truyền `requestId` **tường minh** vào service/job, rồi đặt MDC trong scope cần log.
- Dùng `TaskDecorator` trên đúng executor: capture MDC lúc **submit**, install trên worker, restore trong `finally`.
- Dùng Micrometer Context Propagation/`ContextPropagatingTaskDecorator` nếu hệ thống có observation/tracing context và accessor được đăng ký phù hợp.

Ví dụ fragment về scope đơn giản:

~~~java
String requestId = (String) request.getAttribute("requestId");

executor.execute(() -> {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", requestId);
        service.execute();
    } finally {
        if (previous == null) MDC.remove("requestId");
        else MDC.put("requestId", previous);
    }
});
~~~

Đây là fragment; `executor` và `service` phải được cấu hình thực tế. Với background job kéo dài sau request, nên gửi **immutable business context** cho job, không giữ tham chiếu `HttpServletRequest` hay `ServletRequestAttributes` qua thời gian dài.

## 5. Chọn nơi ghi log

### 5.1. Những thông tin đáng log

Nên dùng log có cấu trúc hoặc key-value:

~~~text
event=http_request_completed
requestId=2f7c7b2b-f418-4297-b042-c86f86e76053
method=GET route=/api/orders/{id} status=200 durationMs=12.4
~~~

`route` nên là template, không phải path có ID thực, query raw hay token. Nếu MVC chưa chọn handler, filter không biết template, có thể log method + status + duration + requestId mà không cần raw URL. Nếu cần tuyến đường từ reverse proxy, áp dụng allowlist/redaction.

**Không log mặc định:** `Authorization`, `Cookie`, `Set-Cookie`, password, access token, raw request/response body, `?resetToken=...`, SQL credentials hay PII. Với một số nghiệp vụ có yêu cầu audit, tách audit log có chính sách bảo vệ/retention và quyền truy cập riêng.

### 5.2. Chọn filter cho dispatch log

~~~java
long started = System.nanoTime();
try {
    chain.doFilter(request, response);
} finally {
    long elapsed = System.nanoTime() - started;
    log.info("dispatch finished status={} elapsedMs={}",
             response.getStatus(), elapsed / 1_000_000.0);
}
~~~

Dùng `System.nanoTime()` (monotonic clock) để đo khoảng thời gian; không trừ `System.currentTimeMillis()` nếu cần elapsed chính xác, vì wall clock có thể thay đổi.

**Ranh giới quan trọng:** với Servlet async, `chain.doFilter` trên initial REQUEST dispatch có thể trả về ngay sau khi MVC **bắt đầu** async, trước khi kết quả sẵn sàng. Vì vậy phép đo trên là **dispatch duration**, không chắc là end-to-end HTTP latency.

### 5.3. Chọn interceptor khi cần route template

Sau khi handler mapping thành công:

~~~java
Object route =
        request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
String routePattern = route instanceof String s ? s : "unmapped";
~~~

Nếu dùng method handler names hoặc business route metadata thì interceptor có vị trí thuận lợi hơn. Đối với metric labels, dùng `routePattern` có số lượng hữu hạn, không dùng từng URL cụ thể (ví dụ `/users/1234`, `/users/1235` gây cardinality cao).

**Cẩn thận:** URI template attribute có thể thay đổi/tồn tại khác nhau theo handler mapping; luôn có fallback. Interceptor không xử lý mọi request bị từ chối trước mapping; đừng dùng một interceptor đơn lẻ làm access log toàn diện.

## 6. Đo thời gian: đo cái gì?

Một request có thể gồm các thành phần:

~~~text
Client
  -> proxy / network
  -> Servlet Filter + Spring Security
  -> MVC mapping + interceptor
  -> controller
  -> service + database/downstream
  -> JSON serialization / view render
  -> response output
  -> client
~~~

Các phép đo khác nhau có ý nghĩa khác nhau:

| Phép đo | Thường bắt đầu/kết thúc ở đâu | Có tính network bên ngoài app? |
| --- | --- | --- |
| Gateway latency | Proxy nhận đến lúc proxy hoàn tất response | Có thể tính nhiều phần mạng/proxy |
| Server HTTP latency | HTTP server/framework observation lifecycle | Không phải toàn network client |
| Filter dispatch duration | Trước/sau `chain.doFilter` của **một dispatch** | Không; có thể bỏ phần async chờ |
| MVC handler elapsed | `preHandle` đến completion theo lifecycle | Không tính giai đoạn trước handler mapping |
| Service duration | Bắt đầu/kết thúc service operation | Chỉ business/service |
| Database/client span duration | Tới lúc dependency call kết thúc | Tùy instrumentation, không phải toàn request |

Không gọi "filter time = controller time" hay "service time = HTTP time". Đừng tính elapsed bằng cách cộng nhiều timers lồng nhau, vì chúng chồng lấp; ví dụ HTTP span đã bao gồm service span.

### 6.1. Đo MVC bằng interceptor

Ví dụ:

~~~java
public boolean preHandle(
        HttpServletRequest request, HttpServletResponse response,
        Object handler) {
    if (request.getAttribute(START_KEY) == null) {
        request.setAttribute(START_KEY, System.nanoTime());
    }
    return true;
}

public void afterCompletion(
        HttpServletRequest request, HttpServletResponse response,
        Object handler, Exception ex) {
    Long start = (Long) request.getAttribute(START_KEY);
    if (start != null) {
        double elapsedMs = (System.nanoTime() - start) / 1_000_000.0;
        log.info("mvc_handler_complete status={} elapsedMs={}",
                 response.getStatus(), elapsedMs);
    }
}
~~~

Đây là fragment — `START_KEY`, `log` và class bao quanh phải được định nghĩa. Điểm cần chú ý ở request async: `preHandle` có thể gọi lần nữa khi ASYNC dispatch, vì vậy chỉ set start khi chưa tồn tại để không reset đồng hồ.

### 6.2. AsyncHandlerInterceptor và ASYNC dispatch

Spring MVC hỗ trợ:

~~~java
public interface AsyncHandlerInterceptor extends HandlerInterceptor {
    default void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception {
    }
}
~~~

Trong request bắt đầu async, Servlet thread ban đầu quay lại pool và MVC gọi **`afterConcurrentHandlingStarted` thay cho `postHandle` và `afterCompletion`** ở lượt dispatch ban đầu. Khi kết quả sẵn sàng, container làm ASYNC dispatch và interceptor thường được gọi lại, cuối cùng `afterCompletion` mới chạy.

~~~text
REQUEST dispatch:
   interceptor.preHandle  -> controller returns Callable/DeferredResult
   interceptor.afterConcurrentHandlingStarted
   Servlet thread released; response chưa nhất thiết hoàn tất

Worker / callback:
   Tạo async result

ASYNC dispatch:
   interceptor.preHandle (lần nữa)
   MVC xử lý result
   interceptor.postHandle / afterCompletion
~~~

Một số trường hợp timeout, lỗi mạng hoặc async completion không qua redispatch theo dự kiến có thể khiến `afterCompletion` **không xảy ra**; nếu cần tổng thời gian chính xác và callback cleanup, dùng `CallableProcessingInterceptor`, `DeferredResultProcessingInterceptor`, `DeferredResult.onTimeout/onCompletion` hoặc Servlet `AsyncListener` theo trường hợp.

**Không đặt cleanup ThreadLocal duy nhất vào `afterCompletion` khi async đã bắt đầu:** Servlet thread ban đầu có thể được tái sử dụng trước đó. Lúc `afterConcurrentHandlingStarted` có thể cần cleanup những thread-bound attributes do interceptor tự thiết lập.

### 6.3. Filter và dispatcher types

Servlet dispatch có các loại như `REQUEST`, `ASYNC` và `ERROR`. `OncePerRequestFilter` có các hook:

~~~java
protected boolean shouldNotFilterAsyncDispatch();
protected boolean shouldNotFilterErrorDispatch();
~~~

Ý nghĩa:

- "Once" là một lần theo **dispatch** và chính sách lọc tương ứng, không phải cam kết chạy đúng một lần cho toàn bộ vòng đời HTTP request bất kể async/error.
- Nếu muốn filter góp mặt trong ASYNC/ERROR dispatch, cần cả cấu hình đăng ký filter cho dispatcher type tương ứng **và** chính sách shouldNotFilter phù hợp.
- Khi filter chạy lại trong async redispatch, phải **tái sử dụng** request ID lưu ở request attribute, không sinh ID mới cho cùng HTTP request.
- Nếu filter chỉ chạy ở REQUEST dispatch, MDC trong async redispatch có thể vắng; đó không phải bằng chứng ID đã biến mất khỏi request attribute.

Đừng gộp log hai dispatch thành hai HTTP requests; một HTTP request async có thể có nhiều lần dispatch. Nếu bạn muốn một observation cho toàn bộ HTTP lifecycle, ưu tiên Micrometer instrumentation được framework hỗ trợ.

## 7. Micrometer Observation và Tracing: khi không cần tự viết timer

Spring Boot Actuator tích hợp Micrometer Observation cho **metrics, logs correlation và tracing** theo các dependency/instrumentation đã cấu hình. Với Boot 3.5 có thể bật cơ chế HTTP server observation/metrics bằng actuator và những registry/exporters phù hợp.

Thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Khi thích hợp, framework có thể tạo observations cho HTTP requests. Sử dụng conventions/tags có sẵn như method, status, URI template để phân tích thay vì thêm interceptor bấm giờ nếu nhu cầu chỉ là **HTTP latency dashboard**.

**Không lạm dụng metric tags**:

- Tags **low-cardinality** có số biến thể hữu hạn (HTTP method, route template, status, outcome).
- Không gắn user ID, email, request ID, raw URL hay token vào metric tags; những giá trị này tạo cardinality rất cao, tăng chi phí và có thể lộ PII.
- Request ID phù hợp với log/tracing context, **không** phù hợp làm dimension của timer/counter.

### 7.1. ObservationRegistry cho đoạn business

Khi muốn đo một bước nghiệp vụ độc lập:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class PricingService {
    private final ObservationRegistry registry;

    public PricingService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public int computePrice(int quantity) {
        return Observation.createNotStarted("pricing.calculate", registry)
                .lowCardinalityKeyValue("kind", "standard")
                .observe(() -> quantity * 100);
    }
}
~~~

Đây là class minh họa tính toán in-memory, không phải endpoint trong dự án mục 9. `Observation` chỉ meaningful khi có observation handlers/metrics/tracing bridge phù hợp trong ứng dụng. Với Spring Boot auto-instrumented HTTP handlers, tránh gắn thêm `@Observed` cho controller mà không hiểu việc nó có thể tạo observation **trùng**.

### 7.2. Tracing qua các service

Một `traceId` được truyền qua HTTP headers chuẩn (thường W3C `traceparent`) nếu client instrumentation/injection đúng. Khi Service A gọi Service B, custom `MDC.put("requestId",...)` trên A **không tự truyền sang B**. Cần HTTP client instrumentation hoặc propagate một header đã được trusted/validated nếu dùng custom ID.

Với `@Async`/thread pool, tracing context cũng có thể mất nếu không propagate. Spring Boot 3.5 hướng dẫn `ContextPropagatingTaskDecorator` trên executor khi cần Micrometer context propagation.

### 7.3. Không nhầm request ID do mình tạo với tracing chính thức

Bạn có thể giữ `X-Request-ID` cho support đồng thời dùng Micrometer trace/span IDs. Trong log, hai loại có thể cùng xuất hiện. Hãy định nghĩa ownership rõ để tránh sinh thêm nhiều ID cạnh tranh, ghi đè context đã do tracing framework quản lý hoặc phát tán headers không đáng tin cậy.

## 8. Logging request/response body: rủi ro và kỹ thuật

Nhu cầu thường gặp: "Log toàn bộ JSON request/response để debug". Với API public, đây là một trong những chỗ dễ lộ password, token, số điện thoại, thông tin thanh toán, personal data và dữ liệu vận hành.

**Không log body mặc định.** Nếu cần kỹ thuật chẩn đoán, chọn field allowlist, sampling, giới hạn kích thước, redaction, hạn thời gian lưu và kiểm soát truy cập. Một phần log bị rò có thể nguy hiểm tương đương dữ liệu DB bị rò.

### 8.1. ContentCachingRequestWrapper

Spring có:

~~~java
ContentCachingRequestWrapper wrapped =
        new ContentCachingRequestWrapper(request, 16 * 1024);
chain.doFilter(wrapped, response);
byte[] cached = wrapped.getContentAsByteArray();
~~~

Cần import `org.springframework.web.util.ContentCachingRequestWrapper`. Wrapper **chỉ cache những byte đã được downstream đọc**; nó không tự hút toàn bộ body trước khi controller chạy. Nếu body chưa được đọc, cache có thể rỗng. Giới hạn cache và overflow handling cần được đánh giá; không log bytes chưa giải mã đúng charset và không coi cache là bản sao hợp lệ của mọi streaming request.

### 8.2. ContentCachingResponseWrapper

Nếu bọc response:

~~~java
ContentCachingResponseWrapper wrapped =
        new ContentCachingResponseWrapper(response);
chain.doFilter(request, wrapped);
// Chỉ minh họa: nếu thật sự cần inspect bytes, phải có policy redaction.
wrapped.copyBodyToResponse();
~~~

Cần import `org.springframework.web.util.ContentCachingResponseWrapper`. **Phải gọi `copyBodyToResponse()`** để truyền body đã buffer xuống response thật, nếu không client có thể không nhận body. Trong async/streaming, việc copy quá sớm hoặc quá muộn có thể làm hỏng response, tăng RAM, phá SSE/file downloads. Chỉ dùng sau khi hiểu lifecycle; với endpoint JSON bình thường cần điều chỉnh cách dùng khi có async dispatch.

### 8.3. Lựa chọn thay thế

- Log metadata method/status/route/elapsed/request ID thay vì body.
- Bật sampling/structured logging trong tầng observability có redaction.
- Dùng `RequestBodyAdvice`/`ResponseBodyAdvice` chỉ khi thật sự cần kiểm tra kiểu DTO cụ thể; nó không bao phủ toàn bộ filter/security/proxy errors hoặc mọi body types.
- Không đặt raw exception stacktrace và request payload vào public error JSON.

## 9. Dự án chạy được: Filter + Interceptor + safe error response

Ví dụ Spring Boot 3.5.0, Java 17, Maven:

1. Filter sinh request ID, đặt header sớm, lưu request attribute và MDC, ghi **filter dispatch time** rồi restore MDC.
2. Interceptor ghi **handler elapsed** và route template, biết HTTP status sau xử lý MVC.
3. Controller chứng minh handler nhìn thấy cùng ID; advice trả JSON an toàn trong một business conflict.
4. Tests xác nhận ID nhất quán, không chấp nhận giá trị spoof từ client, lỗi 409 và hành vi 405/404 của HTTP boundary.
5. Đã thêm Actuator để minh họa hướng production cho HTTP observations; không bắt buộc bạn phải tự viết timer trùng.

### 9.1. Cấu trúc dự án

~~~text
logging-extension-demo/
├── pom.xml
├── src/main/
│   ├── java/demo/LoggingExtensionApplication.java
│   └── resources/application.properties
└── src/test/java/demo/LoggingExtensionTest.java
~~~

Mọi class Java chính trong ví dụ đặt chung một file để dễ copy/run. Trong dự án thật nên tách từng class ra file riêng.

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>logging-extension-demo</artifactId>
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
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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
~~~

### 9.3. application.properties

~~~properties
# Chỉ demo hiện log theo request ID; có thể dùng structured logging ở production.
logging.pattern.level=%5p [rid:%X{requestId}]

# Không tự phát stacktrace/exception details từ /error ra client.
server.error.include-stacktrace=never
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-exception=false

# Actuator mặc định chỉ expose các endpoint an toàn hơn; không mở * bừa.
management.endpoints.web.exposure.include=health,info
~~~

Không cần bật `management.endpoints.web.exposure.include=*` chỉ để xem metrics; quyết định Actuator exposure/authentication theo môi trường. Instrumentation và registry exporter thực tế có thể cần thêm dependencies/cấu hình.

### 9.4. LoggingExtensionApplication.java

Đặt toàn bộ code dưới đây trong `src/main/java/demo/LoggingExtensionApplication.java`. Chỉ có **một** top-level public class trùng tên file; các class còn lại package-private.

~~~java
package demo;

import java.io.IOException;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.AsyncHandlerInterceptor;
import org.springframework.web.servlet.HandlerMapping;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class LoggingExtensionApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoggingExtensionApplication.class, args);
    }
}

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class RequestCorrelationFilter extends OncePerRequestFilter {
    static final String REQUEST_ID_ATTR =
            RequestCorrelationFilter.class.getName() + ".requestId";
    static final String HEADER = "X-Request-ID";

    private static final Logger LOG =
            LoggerFactory.getLogger(RequestCorrelationFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Demo: không dùng giá trị X-Request-ID do client tự cung cấp.
        Object existing = request.getAttribute(REQUEST_ID_ATTR);
        String id = existing instanceof String value
                ? value
                : UUID.randomUUID().toString();

        request.setAttribute(REQUEST_ID_ATTR, id);
        response.setHeader(HEADER, id);

        String previousId = MDC.get("requestId");
        long started = System.nanoTime();

        MDC.put("requestId", id);
        try {
            chain.doFilter(request, response);
        } finally {
            double dispatchMs =
                    (System.nanoTime() - started) / 1_000_000.0;

            // Không log query/body/Authorization/raw path.
            LOG.info("filter_dispatch_done method={} status={} dispatchMs={}",
                    request.getMethod(), response.getStatus(), dispatchMs);

            // Restore vì Servlet thread có thể được tái sử dụng.
            if (previousId == null) MDC.remove("requestId");
            else MDC.put("requestId", previousId);
        }
    }
}

@Component
class HandlerTimingInterceptor implements AsyncHandlerInterceptor {
    private static final Logger LOG =
            LoggerFactory.getLogger(HandlerTimingInterceptor.class);

    private static final String START =
            HandlerTimingInterceptor.class.getName() + ".start";

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        // Khi ASYNC dispatch chạy lại preHandle, không reset mốc bắt đầu.
        if (request.getAttribute(START) == null) {
            request.setAttribute(START, System.nanoTime());
        }
        return true;
    }

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        // Lượt REQUEST đã khởi động async; response chưa hoàn tất.
        // Không kết luận handler đã xong tại đây.
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {
        Object start = request.getAttribute(START);
        if (!(start instanceof Long started)) return;

        double elapsedMs = (System.nanoTime() - started) / 1_000_000.0;

        Object route = request.getAttribute(
                HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
        String pattern = route instanceof String s ? s : "unmapped";

        // Không log exception.getMessage() hay request body.
        LOG.info("mvc_handler_done route={} status={} handlerMs={}",
                pattern, response.getStatus(), elapsedMs);

        request.removeAttribute(START);
    }
}

@Configuration
class MvcLoggingConfig implements WebMvcConfigurer {
    private final HandlerTimingInterceptor interceptor;

    MvcLoggingConfig(HandlerTimingInterceptor interceptor) {
        this.interceptor = interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor)
                .addPathPatterns("/api/**");
    }
}

class OrderConflictException extends RuntimeException {
    OrderConflictException() {
        super("Synthetic internal condition: do not expose raw exception");
    }
}

record ErrorDto(
        String code,
        String message,
        String requestId) {
}

@RestControllerAdvice
class ApiErrors {
    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ErrorDto> onConflict(
            OrderConflictException ex,
            HttpServletRequest request) {

        String requestId =
                (String) request.getAttribute(
                        RequestCorrelationFilter.REQUEST_ID_ATTR);

        // Không trả ex.getMessage() ra client.
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ErrorDto(
                        "ORDER_CONFLICT",
                        "Thao tác không hợp lệ trong trạng thái hiện tại.",
                        requestId));
    }
}

@RestController
@RequestMapping("/api")
class OrderController {
    @GetMapping("/orders/{id}")
    Map<String, Object> find(@PathVariable long id) {
        String requestId = MDC.get("requestId");
        // Demo synchronous: MDC được filter thiết lập trên Servlet thread.
        return Map.of("id", id,
                "status", "ok",
                "requestId", requestId);
    }

    @GetMapping("/orders/conflict-demo")
    Map<String, Object> conflict() {
        throw new OrderConflictException();
    }
}
~~~

**Chú ý về thứ tự mapping:** `GET /api/orders/conflict-demo` có mapping literal nên Spring MVC ưu tiên đường dẫn tĩnh đó trước mapping `/api/orders/{id}`. Route template trong interceptor cho endpoint chi tiết sẽ là `/api/orders/{id}`, tránh metric mỗi order id một nhãn.

**Chú ý về thời gian:** trong code, `dispatchMs` là thời gian của filter chain trên current dispatch. Với synchronous request, nó gần với thời gian xử lý HTTP bên trong ứng dụng nhưng không tính network/client rendering. `handlerMs` bắt đầu sau mapping, kết thúc ở MVC afterCompletion; chúng **không được cộng với nhau**. Với async, phần đo filter ban đầu chưa phản ánh toàn bộ chờ async; interceptor dùng START attribute cho đến final ASYNC dispatch, nhưng nếu async timeout/error không redispatch, cần callback chuyên biệt để tránh thiếu số liệu.

### 9.5. Chạy và quan sát logs

Trong thư mục `logging-extension-demo`:

~~~bash
mvn spring-boot:run
~~~

Thử GET:

~~~bash
curl -i 'http://localhost:8080/api/orders/42'
~~~

Ví dụ body:

~~~json
{"id":42,"status":"ok","requestId":"2f7c7b2b-f418-4297-b042-c86f86e76053"}
~~~

Header `X-Request-ID` cùng HTTP response phải **khớp chính xác** body.requestId; UUID khác ở mỗi request. Console logs có dạng gần như:

~~~text
INFO [rid:2f7c7b2b-f418-4297-b042-c86f86e76053]
mvc_handler_done route=/api/orders/{id} status=200 handlerMs=3.12

INFO [rid:2f7c7b2b-f418-4297-b042-c86f86e76053]
filter_dispatch_done method=GET status=200 dispatchMs=8.45
~~~

Số đo/time/id trong ví dụ **chỉ minh họa** và không phải output cố định; environment, JIT, templates và JVM warm-up làm timing thay đổi theo lượt gọi.

### 9.6. Thử lỗi, spoofed header và 405

Giả sử một client tự gửi X-Request-ID:

~~~bash
curl -i 'http://localhost:8080/api/orders/42' \
  -H 'X-Request-ID: attacker-chosen'
~~~

Server sẽ tạo UUID mới thay vì dùng `attacker-chosen`. Điều đó giảm nguy cơ log spoofing/collision từ HTTP client.

Thử domain conflict:

~~~bash
curl -i 'http://localhost:8080/api/orders/conflict-demo'
~~~

HTTP 409, response body tương đương:

~~~json
{
  "code": "ORDER_CONFLICT",
  "message": "Thao tác không hợp lệ trong trạng thái hiện tại.",
  "requestId": "2f7c7b2b-f418-4297-b042-c86f86e76053"
}
~~~

ID cụ thể sẽ khác và bằng response header `X-Request-ID`. Test cũng cần xác nhận không có chuỗi `"Synthetic internal condition"` trong body.

Thử không có POST mapping:

~~~bash
curl -i -X POST 'http://localhost:8080/api/orders/42'
~~~

Framework thường trả **405 Method Not Allowed**. Filter vẫn có thể thêm X-Request-ID cho request này dù không có handler method thực sự được gọi. Vì interceptor không đảm bảo thấy mọi lỗi trước mapping, nên không dùng nó làm access log duy nhất.

### 9.7. MockMvc tests: request ID, status và an toàn phản hồi

Tạo file `src/test/java/demo/LoggingExtensionTest.java`:

~~~java
package demo;

import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoggingExtensionTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void idMatchesHeaderAndJsonBody() throws Exception {
        MvcResult result = mvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andReturn();

        String id = result.getResponse().getHeader("X-Request-ID");
        assertNotNull(id);
        UUID.fromString(id);

        JsonNode body = mapper.readTree(
                result.getResponse().getContentAsString());
        assertEquals(id, body.path("requestId").asText());
        assertEquals(42, body.path("id").asInt());
    }

    @Test
    void ignoresUntrustedClientRequestId() throws Exception {
        MvcResult result = mvc.perform(get("/api/orders/42")
                .header("X-Request-ID", "attacker-chosen"))
            .andExpect(status().isOk())
            .andReturn();

        String id = result.getResponse().getHeader("X-Request-ID");
        assertNotNull(id);
        UUID.fromString(id);
        assertFalse("attacker-chosen".equals(id));
    }

    @Test
    void conflictKeepsHttpStatusAndHidesInternalMessage()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/api/orders/conflict-demo"))
            .andExpect(status().isConflict())
            .andReturn();

        String id = result.getResponse().getHeader("X-Request-ID");
        assertNotNull(id);

        String serialized = result.getResponse().getContentAsString();
        JsonNode body = mapper.readTree(serialized);

        assertEquals("ORDER_CONFLICT", body.path("code").asText());
        assertEquals(id, body.path("requestId").asText());
        assertFalse(serialized.contains("Synthetic internal condition"));
    }

    @Test
    void filterCoversMethodNotAllowedBeforeHandler()
            throws Exception {
        MvcResult result = mvc.perform(post("/api/orders/42"))
            .andExpect(status().isMethodNotAllowed())
            .andReturn();

        assertNotNull(result.getResponse().getHeader("X-Request-ID"));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

MockMvc tests minh họa phản hồi HTTP và filter registration. Chúng không chứng minh latency thực tế hoặc độ chính xác của metrics khi chạy tải cao. Để kiểm thử logs, dùng in-memory test appender hoặc structured log capture được cách ly khỏi thông tin nhạy cảm; để kiểm thử async, thêm controller có `Callable`/`DeferredResult` và test `asyncDispatch` + timeout callbacks.

## 10. Async và lỗi trước MVC: thiết kế bổ sung

Nếu hệ thống có nhiều async endpoints hoặc streaming, **không chỉ dựa trên ví dụ synchronous**. Một số tình huống:

### 10.1. @Async và CompletableFuture

Method `@Async` chạy trên executor khác; MDC requestId từ filter không tự sang worker. Có thể dùng TaskDecorator:

~~~java
public final class RequestIdTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        String requestId = MDC.get("requestId"); // Capture lúc submit.
        return () -> {
            String previous = MDC.get("requestId");
            try {
                if (requestId == null) MDC.remove("requestId");
                else MDC.put("requestId", requestId);
                task.run();
            } finally {
                if (previous == null) MDC.remove("requestId");
                else MDC.put("requestId", previous);
            }
        };
    }
}
~~~

Đây là class Java cần import `org.springframework.core.task.TaskDecorator` và `org.slf4j.MDC`. Đăng ký bằng `ThreadPoolTaskExecutor#setTaskDecorator(...)` trên **đúng executor** chạy task. Không truyền toàn bộ `ServletRequestAttributes` vào job nền sau response.

### 10.2. @ControllerAdvice không bao phủ mọi lỗi

Một `@RestControllerAdvice` phù hợp để map domain exceptions ở controller/service sang HTTP body. Nhưng:

- Spring Security authentication errors có thể được xử lý **trong filter chain**, trước DispatcherServlet. Cấu hình `AuthenticationEntryPoint`/`AccessDeniedHandler` trong Security.
- Một JSON serialization failure có thể xảy ra khi response đã commit; không còn chắc thay body lỗi được.
- Gateway/proxy có thể tự phát 502/503/504 khi upstream unreachable; cấu hình lỗi Boot không kiểm soát được chúng.

Đây là lý do request ID nên được gắn sớm ở filter hoặc gateway, không chỉ trong advice. Nếu proxy cũng gắn ID, cần có hợp đồng về nguồn tin cậy/format/propagation.

### 10.3. Exception trong filter

Nếu filter gọi dependency rồi throw exception trước `DispatcherServlet`, `@RestControllerAdvice` thường không bắt được vì không qua MVC handler invocation. Đừng đặt business logic phức tạp trong filter. Nếu filter cần xử lý lỗi, hãy để container/security error handler hoặc một policy lỗi ở filter boundary xử lý đúng và tránh lộ exception internals.

### 10.4. Thứ tự filter và Security

Khi có `DelegatingFilterProxy`/Spring Security, request-id filter có thể chạy trước hoặc sau security chain tùy order. Nếu muốn ID trên cả 401/403, bạn phải bảo đảm filter bao phủ đường từ chối security **ở ngoài/đủ sớm**, hoặc để trusted gateway tạo ID; kiểm chứng bằng integration tests. Đừng suy ra từ một `@Order` duy nhất rằng mọi registration giữa Boot, servlet container và security đã đúng trong mọi deployment.

### 10.5. Response header và thời điểm ghi

- Đặt `X-Request-ID` ở **đầu filter chain** khi response chưa commit.
- Đặt "X-Elapsed-Ms" trong `afterCompletion` có thể quá muộn: JSON đã được ghi hoặc response đã commit. Nếu buộc expose duration header, cần hook sớm hơn/response wrapper phù hợp và kiến trúc cho async/streaming; cách đơn giản hơn là **không công bố latency header** và dùng metrics/logs.
- Với streaming, SSE, file download, đo "request complete" cần xét lúc stream/connection kết thúc; không dùng thời gian controller method trả về làm duration tổng.

## 11. Những lỗi phổ biến

1. **Dùng interceptor để cấp quyền duy nhất:** request có thể bị xử lý/truy cập qua đường không match interceptor; dùng Spring Security/filter chain.
2. **Dùng filter để log route template khi handler chưa map:** lúc đó filter thường chỉ có raw URL, dễ dính PII/cardinality. Nếu cần handler route, log ở interceptor hoặc instrumentation của MVC.
3. **Đo `chain.doFilter` rồi gọi đó là latency async end-to-end:** Servlet async initial dispatch có thể kết thúc trước request.
4. **Tạo request ID ngay trong controller:** lỗi trước controller có thể không có ID.
5. **Tin `X-Request-ID` từ client không kiểm tra:** dễ collision, injection, spoofing.
6. **Quên `MDC.remove`/restore trong finally:** pooled thread có thể giữ ID request trước.
7. **Cho rằng MDC tự đi vào `@Async`:** cần explicit context hoặc decorator/snapshot.
8. **Đưa request ID vào metric label:** mỗi request một label, cardinality bùng nổ.
9. **Log toàn bộ query/body/headers:** dễ lộ tokens/PII; mặc định dùng allowlist metadata.
10. **Dùng `ContentCachingResponseWrapper` nhưng quên `copyBodyToResponse()`:** client có thể nhận body trống.
11. **Dùng RequestCachingWrapper rồi tưởng nó đọc body sẵn:** cache chỉ chứa bytes downstream đã đọc.
12. **Đặt header ở `postHandle` hoặc `afterCompletion`:** với `@ResponseBody` body có thể đã commit.
13. **Tạo timer interceptor trùng với Micrometer instrumentation:** metrics double-count, tăng chi phí.
14. **Làm timer bằng `System.currentTimeMillis()`:** wall-clock có thể nhảy; dùng `System.nanoTime()`.
15. **Không quan tâm ASYNC/ERROR dispatch và filter registration:** log thành hai requests hoặc mất correlation ID.
16. **Log `exception.getMessage()` từ DB và gửi lại client:** rò hạ tầng; dùng safe error DTO và secure logs.
17. **Để business logic vào filter:** khó test, ảnh hưởng bảo mật/lifecycle và bypass transaction/service boundary.
18. **Không theo dõi exception/timeouts trong async processing:** `afterCompletion` có thể không chạy ở mọi exceptional async path.
19. **Nhầm requestId với traceId:** custom ID không tự tạo distributed spans và không tự đi qua các HTTP service.
20. **Tin rằng một test MockMvc chứng minh production logging đầy đủ:** còn container/gateway/security/CORS/streaming/lifecycle cần integration tests.

## 12. Checklist thực hành triển khai

- **Mục đích rõ:** cần request ID, access logs, handler logs, business timing hay distributed tracing?
- **Ownership:** gateway hay app sinh request ID? Header nào được tin cậy? Ai quản lý MDC?
- **Ranh giới:** chọn Filter trước MVC, Interceptor sau mapping, Advice cho exception, Micrometer cho observations.
- **Timing:** định nghĩa đúng start/end cho request đồng bộ và async; không tự cộng timers lồng nhau.
- **Privacy:** chỉ log field cho phép; không in Authorization, Cookie, raw URL/query/body, secret.
- **Cardinality:** metric tags dùng route template, HTTP method/status/outcome; không dùng user ID/request ID.
- **Lifecycle:** restore MDC cuối dispatch; khi đổi thread dùng context propagation; khi ERROR/ASYNC dispatch kiểm tra registration.
- **Security:** bảo đảm 401/403 có request ID nếu policy yêu cầu; interceptor không là auth layer.
- **Error:** advice không trả stacktrace/SQL; exception filter/serializer/proxy có policy riêng.
- **Overhead:** sampling, log levels, executor queue, instrumentation cost, retention và quyền xem logs.
- **Tests:** GET thành công, 400/404/405, security denial, exception 500, async completion/timeout, nhiều request concurrent; so header ID ↔ body/log và kiểm tra không lộ PII.
- **Operation:** dashboard latency theo p50/p95/p99, tỷ lệ 4xx/5xx, theo route/status, traces cho yêu cầu chậm; biết cách tra log qua request ID.

## 13. Bài tập

**Bài 1 — Chọn điểm mở rộng:** Với từng yêu cầu, chọn Filter, Interceptor, ControllerAdvice, ResponseBodyAdvice hay Micrometer: (a) sinh request ID cho cả 401/403, (b) ghi template `/orders/{id}`, (c) chuẩn hóa lỗi 409, (d) đo HTTP p95 và (e) thêm field tùy chỉnh vào DTO JSON.

**Bài 2 — Timing:** Controller trả `Callable<ResponseEntity<?>>` và mất 1 giây trong worker, initial filter dispatch chỉ chạy 10 ms. Vì sao timer ở finally filter có thể log 10 ms thay vì ~1 giây? Cần dùng callback/instrumentation nào để đo request HTTP hoàn chỉnh?

**Bài 3 — MDC:** Hai requests liên tiếp được xử lý bằng cùng thread. Nếu quên `finally` restore MDC, log request thứ hai có thể xuất hiện ID nào? Viết đoạn capture/restore cẩn thận khi task ném exception.

**Bài 4 — Tracing:** Service A trả HTTP request ID cho client và gọi Service B. Vì sao B không tự thấy cùng traceId? Nêu cơ chế trace context propagation qua HTTP client/gateway và phân biệt custom request ID với distributed trace.

**Bài 5 — Log redaction:** Một request có `Authorization: Bearer ...`, `?resetToken=...`, JSON password. Thiết kế một log line an toàn gồm method/status/route template/elapsed/requestId nhưng không có các giá trị nhạy cảm.

**Bài 6 — Interceptor:** Nếu Controller trả JSON, `postHandle` có phải vị trí an toàn để set response header không? Giải thích khi nào response đã commit và chọn filter/ResponseBodyAdvice nếu cần.

**Bài 7 — Unit/MockMvc:** Mở rộng `LoggingExtensionTest` để xác nhận UUID giữa header và body luôn khớp, và không bao giờ là `attacker-chosen` khi client tự gửi ID.

**Bài 8 — Metrics:** Nếu bạn đặt label `userId` cho mỗi http.server.requests timer thì chuyện gì xảy ra với số lượng time series? Đề xuất bộ tag ít cardinality hơn.

**Bài 9 — Async dispatch:** Viết một endpoint `Callable<String>` và AsyncHandlerInterceptor có stopwatch gắn request attribute. Quan sát callbacks REQUEST/ASYNC dispatch và test bằng `asyncDispatch`.

**Bài 10 — Architecture:** Một ứng dụng có Spring Security, MVC, Actuator, 10 service downstream và một gateway. Vẽ nơi tạo request ID, nơi inject/extract tracing headers, nơi đo HTTP, nơi đo service span, nơi redaction. Tránh instrument một việc hai lần.

## 14. Ghi nhớ

- **Servlet Filter** là ranh giới phù hợp cho request ID, MDC và ghi log ở mức request dispatch; nó hoạt động trước MVC nhưng không nhất thiết biết handler template.
- **HandlerInterceptor** phù hợp cho route/handler-aware logging và đo phạm vi MVC; nó không thay thế security filter.
- **AsyncHandlerInterceptor** cần xét callback `afterConcurrentHandlingStarted` và redispatch; filter `chain.doFilter` ban đầu không chắc đo được toàn bộ HTTP async latency.
- **Micrometer Observation/Tracing** là hướng mặc định tốt cho HTTP metrics và distributed traces; không tự thêm timers/tags trùng, tránh cardinality cao.
- **MDC** dùng cho log correlation, phải dọn; muốn propagate sang thread khác cần TaskDecorator/snapshot hoặc explicit parameters.
- **Request ID** nên được tạo/kiểm soát bởi server/trusted gateway, xuất header sớm, dùng nhất quán trong logs và safe error response.
- **Đo thời gian đúng ranh giới, log đúng dữ liệu, dọn đúng vòng đời** quan trọng hơn số lượng interceptor/filter được thêm vào.

## 15. Tài liệu tham khảo

- [Spring Framework 6.2 — Servlet Filters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): filter và các đặc điểm lifecycle.
- [Spring Framework 6.2 — Interceptors](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html): WebMvcConfigurer và interceptor registration.
- [Spring Framework 6.2 — Handler Interception](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html): preHandle, postHandle, afterCompletion, response handling.
- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Callable, DeferredResult, AsyncHandlerInterceptor, ASYNC dispatch.
- [Spring Framework 6.2 — OncePerRequestFilter](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): REQUEST/ASYNC/ERROR dispatcher behavior.
- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html): Micrometer Observation, metrics, tracing, context propagation.
- [Spring Boot 3.5 — HTTP Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): distributed tracing và correlation.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent/tracestate.
- [SLF4J Manual — MDC](https://www.slf4j.org/manual.html): log correlation context.

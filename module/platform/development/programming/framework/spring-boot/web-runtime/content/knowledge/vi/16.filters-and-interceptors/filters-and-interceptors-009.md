# Truyền mã tương quan và đo thời gian xử lý theo yêu cầu trong Spring Boot

## 1. Vì sao cần một mã tương quan và một phép đo thời gian đáng tin?

Khi client gọi GET /api/orders/42, nhiều thành phần có thể cùng tham gia xử lý: API gateway, Servlet Filter hoặc WebFlux WebFilter, Spring Security, DispatcherServlet hoặc DispatcherHandler, interceptor, controller, service, database và HTTP client gọi dịch vụ khác. Nếu request lỗi hoặc chậm, một dòng log đơn lẻ thường không đủ giải thích toàn bộ câu chuyện.

Hai nhu cầu xuất hiện cùng nhau:

1. **Correlation ID (mã tương quan):** gắn các log và những lần gọi liên quan vào cùng một tương tác để tra cứu, hỗ trợ người dùng và điều tra lỗi.
2. **Request duration (thời gian xử lý):** đo một khoảng thời gian xác định, ví dụ từ lúc tầng HTTP của ứng dụng nhận request đến khi response hoàn thành, để theo dõi latency, SLO và nguyên nhân chậm.

Hai khái niệm độc lập: correlation ID là **định danh**; duration là **số đo**. Một correlation ID không phải timestamp, không thay thế distributed trace ID và không chứng minh request nhanh/chậm. Một phép đo duration không tự cung cấp khả năng truy vết qua nhiều service.

Đề bài nằm trong nhóm **Bộ lọc và interceptor**, vì vậy trọng tâm là chọn đúng điểm chặn request, bảo đảm vòng đời ID, thời điểm bắt đầu/kết thúc phép đo và truyền ngữ cảnh sang code downstream. Bài bao gồm Spring MVC/Servlet và Spring WebFlux/reactive; cùng yêu cầu nghiệp vụ nhưng API và cách truyền context khác nhau.

### 1.1. Một yêu cầu có thể có nhiều thời gian khác nhau

| Khoảng đo | Bắt đầu | Kết thúc | Diễn giải |
|---|---|---|---|
| Client end-to-end latency | Client chuẩn bị/gửi request | Client nhận xong kết quả | Bao gồm mạng, DNS/TLS có thể có, proxy, server và tải body |
| Gateway latency | Gateway nhận request | Gateway gửi xong response | Bao gồm gateway routing, upstream và network trong phạm vi gateway |
| HTTP server duration | Server observation nhận request | Server hoàn tất HTTP exchange theo instrumentation | Phù hợp với http.server.requests, tùy công cụ/runtime |
| Servlet Filter synchronous duration | Trước filterChain.doFilter | Sau khi lời gọi đó trả/throw | **Không tự bao phủ toàn bộ thời gian async** |
| MVC HandlerInterceptor duration | preHandle | afterCompletion khi được gọi | Thường đo phần MVC handler processing; có giới hạn async/error |
| Controller method duration | Trước khi gọi method | Khi method Java trả về | Không nhất thiết bao gồm thời gian publisher/Callable hoàn tất |
| Downstream HTTP client duration | Bắt đầu outbound exchange | Kết thúc response exchange | Chỉ đo một lời gọi tới upstream |
| Database query duration | Trước query | Sau query | Chỉ một đoạn của server processing |

Không cộng tất cả các metric như những đại lượng độc lập: các khoảng có thể **lồng nhau**, cùng đếm một khoảng thời gian hoặc có cơ chế sampling khác nhau. Trước khi chọn một field tên durationMs, phải định nghĩa nó đo phạm vi nào.

### 1.2. Ví dụ hành trình một request

~~~text
Browser / Mobile Client
   |
   | X-Correlation-ID (nếu được tin cậy/cho phép)
   | traceparent (nếu dùng distributed tracing)
   v
API Gateway / Trusted Ingress
   |
   v
HTTP Server: Tomcat hoặc Reactor Netty
   |
   +-- Filter/WebFilter: xác định correlationId, gắn response header
   |
   +-- Security filter chain / authentication
   |
   +-- DispatcherServlet / DispatcherHandler
   |
   +-- HandlerInterceptor (MVC), controller/router
   |
   +-- Service
   |      |
   |      +-- HTTP client -> Downstream service
   |      |      cùng correlation policy / W3C trace context
   |      |
   |      +-- Database / cache
   |
   +-- Response; ghi duration + status + route + correlationId
   |
   v
Client nhận status/body và X-Correlation-ID
~~~

Mỗi mũi tên chỉ mối quan hệ luồng xử lý; không có ý nghĩa rằng mọi đoạn được thực thi đồng bộ trên một Java thread. Với WebFlux và xử lý async ở MVC, request có thể đi qua nhiều thread/dispatch trước khi hoàn tất.

## 2. Correlation ID, Request ID, Trace ID, Span ID và Idempotency-Key

| Khái niệm | Mục đích | Phạm vi | Có dùng làm khóa nghiệp vụ không? |
|---|---|---|---|
| Correlation ID | Gom các bước/log liên quan đến một tương tác | Do tổ chức xác định; có thể theo một request hoặc một giao dịch nhiều request | Không |
| Request ID | Định danh riêng một HTTP request | Thường một hop/request, do gateway/server cấp | Không |
| W3C trace ID | Định danh một distributed trace | Nhiều service/spans thuộc một trace | Không |
| Span ID | Định danh một operation/span | Một phần trong trace | Không |
| Idempotency-Key | Deduplicate một thao tác có side effect khi retry | Theo API contract, chủ thể, operation, payload và TTL | **Có semantics riêng**, không phải correlation |

Một hệ thống có thể chủ động dùng request ID làm correlation ID, hoặc chọn trace ID làm giá trị tra cứu nếu instrumentation thống nhất. Nhưng không mặc nhiên coi chúng tương đương: một nghiệp vụ có thể trải qua nhiều HTTP requests, một trace có thể có nhiều spans, một request được retry có thể tạo nhiều attempts.

Ví dụ W3C traceparent:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Trong header này, trace-id có 32 chữ số hex, parent-id có 16 chữ số hex, và trace flags theo tiêu chuẩn. **Đừng tự sửa traceparent để thay correlation ID**. Nếu dùng Micrometer Tracing/OpenTelemetry, để instrumentation tạo, trích xuất và lan truyền trace context theo W3C. Header ứng dụng như X-Correlation-ID có thể tồn tại song song.

### 2.1. Tên header cần có hợp đồng

Một số hệ thống dùng X-Correlation-ID, một số dùng X-Request-ID hoặc một tên nội bộ khác. Chọn một tên chuẩn toàn hệ thống và áp dụng nhất quán giữa gateway, Java services, mobile/web client, log exporter và support.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Correlation-ID: req-example12345

{"message":"ok"}
~~~

Đây là response **minh họa**, không phải nội dung tự động được Spring Boot tạo ra khi chưa viết Filter/WebFilter hoặc cấu hình gateway. Mã phải hợp lệ về cú pháp header, không chứa ký tự điều khiển hoặc dữ liệu nhạy cảm.

### 2.2. ID nên được cấp ở đâu?

Ưu tiên cấp ID tại **trusted ingress** như gateway, rồi truyền sang các backend. Nếu ứng dụng được truy cập trực tiếp, chính ứng dụng có thể sinh ID. Một chính sách phổ biến:

1. Chỉ nhận header từ nguồn được tin cậy hoặc validate và áp dụng chính sách xác thực rõ ràng.
2. Giới hạn độ dài và bộ ký tự, loại bỏ/không tin giá trị chứa CR/LF, Unicode điều khiển hoặc quá dài.
3. Nếu không có ID hợp lệ, sinh ID mới, ví dụ UUID ngẫu nhiên.
4. Đặt ID vào request context trước khi các thành phần cần log chạy.
5. Trả ID trong response header; khi trả ProblemDetail lỗi, cũng có thể đặt extension correlationId trong body.
6. Truyền ID khi gọi downstream theo contract.
7. Xóa/khôi phục trạng thái thread-local sau request để không rò ID sang request khác.

Ví dụ whitelist cho demo Java là [A-Za-z0-9._-]{8,64}. Đây **không phải một tiêu chuẩn toàn cầu**, chỉ là policy minh họa. Trong API public, chỉ kiểm tra format **không làm incoming ID trở thành đáng tin**. Có thể luôn sinh internal ID mới và lưu external ID chưa tin cậy vào một field khác.

### 2.3. Không dùng correlation ID để quyết định quyền

Không dùng ID để đăng nhập, xác định tenant, nhận diện user, cấp quyền hay xác nhận thanh toán. Correlation ID không phải token bảo mật; một client có thể tự gửi header giả mạo. Không chứa email, số điện thoại, mật khẩu, token hoặc mã tài khoản trong ID.

### 2.4. ID không phải metric tag

Một ID mới cho mỗi request có cardinality gần như vô hạn. Nếu đưa correlationId làm tag cho Timer/counter trong Prometheus hoặc Micrometer, số time series có thể tăng rất nhanh. **Dùng ID trong logs/traces; dùng route template, method, status, outcome và error category hữu hạn trong metrics.**

## 3. Chọn đúng điểm mở rộng: Filter hay HandlerInterceptor?

Trong Spring MVC Servlet stack, hai API thường được dùng cho mục đích này:

| Tiêu chí | Servlet Filter / OncePerRequestFilter | HandlerInterceptor |
|---|---|---|
| Thuộc tầng | Servlet container filter chain | Spring MVC handler execution chain |
| Chạy trước DispatcherServlet? | Có nếu được đăng ký đúng | Không; chỉ sau khi MVC tìm handler |
| Có thể bao phủ các Servlet khác? | Có nếu URL/dispatcher mapping phù hợp | Không, chỉ MVC handlers |
| Biết MVC handler/controller? | Không có thông tin đầy đủ tại đầu chain | Có đối tượng handler và mapping metadata |
| Thêm correlation response header sớm | Rất phù hợp | Có thể, nhưng không bao phủ mọi route/lỗi |
| Gắn MDC trước security/dispatcher | Có thể, tùy Filter order | Muộn hơn Filter và thường sau security |
| Đo handler execution | Không trực tiếp phân biệt method | Phù hợp với preHandle/afterCompletion |
| Đo toàn HTTP request async chính xác | Không chỉ bằng try/finally quanh doFilter | Không bảo đảm chỉ với afterCompletion |
| Xử lý ERROR/ASYNC dispatch | Phụ thuộc registration và flags | Phụ thuộc MVC handler lifecycle |
| Lỗi ngay tại security/filter | Có thể thấy khi Filter đứng trước | Có thể không vào interceptor |

**Nguyên tắc thực tế:** đặt correlation ID ở một Filter đủ sớm; dùng HandlerInterceptor khi cần handler metadata hoặc xử lý chuyên biệt của MVC; dùng **Spring Boot/Micrometer HTTP server observations** để đo độ trễ toàn exchange khi có Actuator, tránh tự làm lại một meter trùng với instrumentation có sẵn.

### 3.1. OncePerRequestFilter không có nghĩa duy nhất một lần qua toàn bộ async lifecycle

Tên class dễ gây hiểu nhầm. OncePerRequestFilter bảo đảm logic lọc một lần **trong một request dispatch thread** theo quy tắc của nó, không có lời hứa rằng chỉ có đúng một invocation trong mọi ASYNC/ERROR dispatch và mọi Java thread của cùng một HTTP request.

Hai phương thức:

- shouldNotFilterAsyncDispatch() mặc định trả true, nên có thể bỏ qua các ASYNC dispatch tiếp theo.
- shouldNotFilterErrorDispatch() mặc định trả true, nên có thể bỏ qua ERROR dispatch.

Có thể override trả false khi cần khôi phục MDC trên các lượt dispatch tương ứng. Tuy nhiên **FilterRegistrationBean hoặc Servlet container cũng phải map Filter vào DispatcherType.ASYNC/ERROR**; override method một mình không đủ.

Trong một ERROR dispatch lồng bên trong REQUEST dispatch, OncePerRequestFilter có thể đi qua doFilterNestedErrorDispatch thay cho doFilterInternal. Khi xử lý security/logging phức tạp, cần kiểm tra hành vi container thực tế.

### 3.2. HandlerInterceptor với request async

Đối với MVC async processing như Callable hoặc DeferredResult, HandlerInterceptor có thể đi theo trình tự:

~~~text
REQUEST dispatch:
    preHandle
    controller trả Callable/DeferredResult
    afterConcurrentHandlingStarted
    -> Filter chain thoát, async work tiếp tục ở nơi khác

ASYNC redispatch khi có kết quả:
    preHandle (có thể được gọi lại)
    Spring MVC ghi kết quả
    afterCompletion
~~~

Bởi vậy, nếu đặt startNanos mới mỗi lần preHandle được gọi, bạn có thể đo lại từ thời điểm redispatch và **mất phần thời gian chờ async**. Nên chỉ đặt startNanos nếu request attribute chưa có.

Không coi afterCompletion là callback được bảo đảm cho mọi lỗi async: timeout hoặc network error có thể xảy ra mà không có redispatch và callback afterCompletion. Nếu cần theo dõi các tình huống ấy khi tự xây instrumentation, dùng các callback qua WebAsyncManager/CallableProcessingInterceptor/DeferredResultProcessingInterceptor hoặc ưu tiên server observations đã được framework tích hợp.

## 4. Đo thời gian: System.nanoTime thay vì đồng hồ tường

Đo elapsed duration bằng **monotonic time source** như System.nanoTime() trong cùng JVM:

~~~java
long startNanos = System.nanoTime();

// Thực thi một tác vụ...

long durationNanos = System.nanoTime() - startNanos;
double durationMs = durationNanos / 1_000_000.0;
~~~

Đây là snippet. System.nanoTime không biểu diễn một ngày/giờ thực mà chỉ dùng để tính chênh lệch. Nó thích hợp hơn System.currentTimeMillis cho latency vì đồng hồ hệ thống có thể được đồng bộ NTP hoặc thay đổi; duration có thể sai nếu lấy hiệu hai mốc wall-clock.

Dùng Instant.now() hoặc timestamp theo UTC khi cần ghi **thời điểm** request, không dùng để đo elapsed duration có độ chính xác cao. Một log có thể chứa cả thời điểm và duration, với mục đích khác nhau.

### 4.1. Đơn vị và độ chính xác

- nanoTime trả một số theo đơn vị nanosecond ở API, nhưng độ phân giải/độ chính xác thực phụ thuộc platform.
- TimeUnit.NANOSECONDS.toMillis trả số nguyên millisecond, có thể bằng 0 đối với operation nhanh; đó không phải chứng minh duration bằng 0.
- Có thể dùng durationNanos / 1_000_000.0 để báo ms với phần thập phân.
- Không so sánh nanoTime được lấy từ hai JVM khác nhau: các origin không có ý nghĩa liên hệ.
- Không cộng latency từ nhiều thành phần mà chưa xác định chúng chạy song song hay lồng nhau.
- Không coi duration của handler method trả Mono/Flux là tổng thời gian response reactive hoàn tất.

### 4.2. Lấy status ở đúng thời điểm

Trong Servlet Filter, response.getStatus() sau filterChain.doFilter có thể là status **tạm thời** nếu request chuyển sang async. Trong WebFlux, response.getStatusCode() có thể vẫn chưa được đặt khi filter được gọi. Hãy ghi status khi response/pipeline hoàn tất theo callback phù hợp; nếu status chưa xác định, log một giá trị trung lập, không đoán 200.

### 4.3. Từ duration đến SLO

Mục tiêu vận hành thường là tỷ lệ lỗi, P50/P95/P99 latency, throughput và saturation theo route. Cần metric distribution/histogram, không chỉ trung bình. Một vài request đặc biệt chậm có thể bị che trong average.

Không ghi một Timer mới vào cùng tên http.server.requests nếu Spring Boot Actuator đã instrument tự động, nếu không có thể đếm kép hoặc tạo các time series cạnh tranh. Dùng observation conventions/customizers khi chỉ muốn thêm các low-cardinality tags.

## 5. Ví dụ Spring Boot 3.x / Java 17+: Correlation Filter trong MVC

Ví dụ này dùng Spring MVC/Servlet với embedded Tomcat thông thường, Java 17+, Spring Boot 3.3.x làm mốc giải thích. Đường dẫn là project mẫu có thể tạo bằng Spring Initializr; lớp Java sử dụng Jakarta Servlet API của Boot 3.x.

### 5.1. Gradle dependencies

Trong project Gradle đã cấu hình Spring Boot plugin và Maven Central:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Actuator cần cho phần metrics; Filter/Interceptor không phụ thuộc riêng vào Actuator. Nếu dùng Maven thì có thể khai báo các starter tương đương.

Cấu trúc project:

~~~text
src/main/java/dev/example/correlationmvc/
    CorrelationMvcApplication.java
    CorrelationIdFilter.java
    HttpPipelineConfig.java
    MvcTimingInterceptor.java
    DemoController.java
src/main/resources/application.yml
src/test/java/dev/example/correlationmvc/
    CorrelationMvcTest.java
~~~

### 5.2. Main class

File src/main/java/dev/example/correlationmvc/CorrelationMvcApplication.java:

~~~java
package dev.example.correlationmvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorrelationMvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorrelationMvcApplication.class, args);
    }
}
~~~

Đặt các class cùng package để component scanning của Spring Boot nhận được đúng cấu hình và controller.

### 5.3. Một Filter giữ ID qua các dispatch

File src/main/java/dev/example/correlationmvc/CorrelationIdFilter.java:

~~~java
package dev.example.correlationmvc;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public class CorrelationIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Correlation-ID";
    public static final String ATTRIBUTE = "correlationId";

    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{8,64}");

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false;
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        Object existing = request.getAttribute(ATTRIBUTE);
        String id;

        if (existing instanceof String saved) {
            id = saved;
        } else {
            String candidate = request.getHeader(HEADER);

            id = candidate != null
                    && SAFE.matcher(candidate).matches()
                    ? candidate
                    : UUID.randomUUID().toString();

            request.setAttribute(ATTRIBUTE, id);
        }

        response.setHeader(HEADER, id);

        String previous = MDC.get(ATTRIBUTE);
        MDC.put(ATTRIBUTE, id);

        try {
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(ATTRIBUTE);
            } else {
                MDC.put(ATTRIBUTE, previous);
            }
        }
    }
}
~~~

Các điểm thiết kế:

1. **Request attribute** giữ ID của request xuyên qua các dispatch; không tạo ID mới mỗi lần ASYNC redispatch.
2. **Response header** được set sớm để response bình thường và nhiều response lỗi có ID nhất quán.
3. **MDC** chỉ gắn trong thời gian Filter chain chạy trên thread hiện tại; finally khôi phục trạng thái trước đó để tránh lẫn ID.
4. Với ASYNC/ERROR dispatch, Filter được phép chạy lại để gắn MDC cho dispatch thread nếu Servlet registration cũng cho phép.
5. Đoạn code **không tự propagation MDC** sang thread của Callable, @Async, CompletableFuture hoặc background executor không đi qua Filter.
6. Policy trong demo chấp nhận inbound ID nếu đúng regex; trên API public cần kiểm soát trusted ingress hoặc tự sinh internal ID để chống giả mạo.

Class cố ý **không gắn @Component**, bởi ta sẽ đăng ký một FilterRegistrationBean minh bạch bên dưới để kiểm soát dispatcher types và filter order. Nếu đồng thời thêm @Component rồi còn đăng ký bean khác, có nguy cơ duplicate/filter-order không như dự kiến.

### 5.4. FilterRegistrationBean và thứ tự

File src/main/java/dev/example/correlationmvc/HttpPipelineConfig.java:

~~~java
package dev.example.correlationmvc;

import java.util.EnumSet;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class HttpPipelineConfig implements WebMvcConfigurer {

    @Bean
    FilterRegistrationBean<CorrelationIdFilter> correlationRegistration() {
        FilterRegistrationBean<CorrelationIdFilter> bean =
                new FilterRegistrationBean<>(
                        new CorrelationIdFilter());

        bean.setName("correlationIdFilter");
        bean.addUrlPatterns("/*");
        bean.setDispatcherTypes(EnumSet.of(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC,
                DispatcherType.ERROR));
        bean.setAsyncSupported(true);
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE);

        return bean;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new MvcTimingInterceptor());
    }
}
~~~

Đây là cấu hình có thể dùng cùng class CorrelationIdFilter ở mục 5.3 và MvcTimingInterceptor ở mục 6. Trong ứng dụng thực có Spring Security, CORS, observations và các filter khác, cần xem order cụ thể thay vì chỉ đặt HIGHEST_PRECEDENCE cho mọi filter.

Cả hai điều kiện phải đúng để Filter chạy lại trong ASYNC/ERROR dispatch: OncePerRequestFilter không bỏ qua dispatch và registration cho phép dispatcher types tương ứng. Không tự đăng ký thêm Filter cùng loại một lần thứ hai.

## 6. HandlerInterceptor đo thời gian MVC handler

Một HandlerInterceptor giúp lấy thông tin **route template** từ HandlerMapping để log và theo dõi logic MVC. Đây là measurement hữu ích cho việc học, nhưng không thay thế built-in server observation để đo toàn bộ request trong mọi lỗi/async lifecycle.

File src/main/java/dev/example/correlationmvc/MvcTimingInterceptor.java:

~~~java
package dev.example.correlationmvc;

import java.util.concurrent.TimeUnit;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.servlet.AsyncHandlerInterceptor;
import org.springframework.web.servlet.HandlerMapping;

public class MvcTimingInterceptor implements AsyncHandlerInterceptor {

    private static final Logger LOG =
            LoggerFactory.getLogger(MvcTimingInterceptor.class);

    private static final String START =
            MvcTimingInterceptor.class.getName() + ".startNanos";

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
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        // Giữ request attribute: async work vẫn chưa hoàn tất.
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {

        Object value = request.getAttribute(START);
        if (!(value instanceof Long started)) {
            return;
        }

        request.removeAttribute(START);

        long nanos = System.nanoTime() - started;
        double milliseconds = nanos / 1_000_000.0;

        Object matched = request.getAttribute(
                HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

        String route = matched == null
                ? "UNMAPPED"
                : matched.toString();

        Object id = request.getAttribute(
                CorrelationIdFilter.ATTRIBUTE);

        LOG.info(
                "mvc_request method={} route={} status={} durationMs={} "
                + "correlationId={} exception={}",
                request.getMethod(),
                route,
                response.getStatus(),
                milliseconds,
                id,
                exception == null
                        ? "none"
                        : exception.getClass().getSimpleName());
    }
}
~~~

Cấu hình WebMvcConfigurer ở mục 5.4 đã đăng ký interceptor này. Khi MVC tìm handler, preHandle được gọi và đặt mốc lần đầu. Nếu request chuyển sang async rồi redispatch, mốc được giữ lại, thay vì tạo lại.

**Giới hạn của demo:**
- HandlerInterceptor chỉ chạy trên các request có MVC handler chain phù hợp; không phải mọi lỗi từ Servlet Filter, Spring Security hoặc gateway.
- Trong các tình huống async timeout/network error không có redispatch, afterCompletion có thể không chạy. Cần callback chuyên biệt hoặc server observation để đo coverage rộng.
- Response status trong log là status tại callback, không bảo đảm bao gồm giai đoạn write network cuối cùng.
- Không ghi trực tiếp raw request URI có biến động không giới hạn vào metric tag; route lấy từ BEST_MATCHING_PATTERN_ATTRIBUTE thường là template, phù hợp hơn cho nhóm theo endpoint.
- Không log error.message hoặc rejected value chứa thông tin nhạy cảm.

### 6.1. Filter và interceptor có tính được cùng duration không?

Không nhất thiết. Filter bọc Servlet chain và có thể chạy cho request không tìm ra MVC handler. Interceptor chỉ chạy sau khi chọn handler và có thể đo từ trước handler tới afterCompletion. Nếu một Filter ghi thời gian tại finally của doFilter còn interceptor ghi ở afterCompletion, hai giá trị có thể khác do filter ordering, dispatch, serialization và async behavior.

Khi xây dashboard P95/P99 cho **HTTP server latency**, nên dùng một nguồn đo thống nhất như Micrometer http.server.requests. Log interceptor có thể là phép đo bổ sung phục vụ debug, không gộp bừa cùng số đo server-level.

## 7. Controller thử nghiệm: request bình thường, lỗi và async

File src/main/java/dev/example/correlationmvc/DemoController.java:

~~~java
package dev.example.correlationmvc;

import java.util.Map;
import java.util.concurrent.Callable;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DemoController {

    @GetMapping("/api/hello")
    public Map<String, String> hello(HttpServletRequest request) {
        Object id = request.getAttribute(
                CorrelationIdFilter.ATTRIBUTE);

        return Map.of(
                "message", "hello",
                "correlationId", String.valueOf(id));
    }

    @GetMapping("/api/async")
    public Callable<Map<String, String>> asyncHello(
            HttpServletRequest request) {

        String id = String.valueOf(request.getAttribute(
                CorrelationIdFilter.ATTRIBUTE));

        return () -> Map.of(
                "message", "async",
                "correlationId", id);
    }

    @GetMapping("/api/fail")
    public void fail() {
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Invalid demo request");
    }
}
~~~

Ở request thường, controller trả JSON body gồm message và correlationId lấy từ request attribute. Ở /api/async, controller trả Callable và Spring MVC sử dụng cơ chế xử lý async. Code chỉ minh họa hành vi; không chạy một tác vụ blocking nặng, không truy cập database.

Trong ví dụ /api/fail, Spring MVC có thể trả HTTP 400. Response body của lỗi do error handling configuration quyết định, nhưng Filter có thể đã gắn X-Correlation-ID vào header. Việc thống nhất toàn bộ JSON lỗi thuộc thiết kế ControllerAdvice/ErrorController riêng.

## 8. application.yml và lệnh chạy MVC demo

File src/main/resources/application.yml:

~~~yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,metrics

logging:
  pattern:
    level: "%5p [correlationId:%X{correlationId:-}]"
~~~

Phần logging.pattern.level của ví dụ dành cho logging setup thường dùng trong Boot/Logback. Nó đưa MDC correlationId vào log pattern. Nếu ứng dụng dùng Micrometer Tracing, Boot còn có thể đưa traceId/spanId vào logging correlation format; hãy kiểm tra cách kết hợp thay vì vô tình ghi đè một pattern quan trọng.

Chạy từ thư mục Gradle project:

~~~bash
./gradlew bootRun
~~~

Trong PowerShell Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Gửi request có ID hợp lệ:

~~~bash
curl -i -H "X-Correlation-ID: req-test12345" \
  http://localhost:8080/api/hello
~~~

Kết quả chính: HTTP 200, response header X-Correlation-ID=req-test12345 và body:

~~~json
{"message":"hello","correlationId":"req-test12345"}
~~~

Thứ tự các JSON fields/headers có thể khác. Dòng log từ interceptor có dạng khái niệm:

~~~text
mvc_request method=GET route=/api/hello status=200 durationMs=3.42 correlationId=req-test12345 exception=none
~~~

**durationMs=3.42 chỉ là số minh họa**: mỗi lượt thực chạy có duration khác. Không test latency bằng cách so sánh một số millisecond cố định.

Gửi không có header:

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Server sinh một UUID mới và dùng cùng giá trị trong response header/body. Gửi header không hợp lệ như chuỗi chứa khoảng trắng, demo sẽ thay bằng UUID. Ở public API nên có chính sách trusted boundary rõ ràng hơn chỉ kiểm tra regex.

Kiểm tra async:

~~~bash
curl -i http://localhost:8080/api/async
~~~

Body thông thường có message="async" và correlationId. Servlet container có thể thực hiện ASYNC redispatch; filter và interceptor được thiết kế không tạo lại ID hay mốc đo khi redispatch. Trong thực tế timeout, disconnect hoặc lỗi async yêu cầu xử lý riêng như đã giải thích.

Kiểm tra lỗi:

~~~bash
curl -i http://localhost:8080/api/fail
~~~

Status mong đợi HTTP 400 và X-Correlation-ID vẫn có trong nhiều đường lỗi MVC thông thường. Không suy đoán JSON body nếu project chưa có một error contract cụ thể.

## 9. Test MockMvc cho header, ID và async dispatch

File src/test/java/dev/example/correlationmvc/CorrelationMvcTest.java:

~~~java
package dev.example.correlationmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorrelationMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void preservesAllowedCorrelationId() throws Exception {
        mvc.perform(get("/api/hello")
                .header("X-Correlation-ID", "req-test12345"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Correlation-ID", "req-test12345"))
                .andExpect(jsonPath("$.correlationId")
                        .value("req-test12345"));
    }

    @Test
    void generatesNewIdWhenHeaderMissing() throws Exception {
        MvcResult result =
                mvc.perform(get("/api/hello"))
                        .andExpect(status().isOk())
                        .andExpect(header().exists("X-Correlation-ID"))
                        .andReturn();

        String id = result.getResponse().getHeader(
                "X-Correlation-ID");

        assertNotNull(id);
        assertEquals(36, id.length());
    }

    @Test
    void rejectsUnsafeHeaderFormat() throws Exception {
        MvcResult result =
                mvc.perform(get("/api/hello")
                        .header("X-Correlation-ID", "bad id"))
                        .andExpect(status().isOk())
                        .andReturn();

        assertNotEquals(
                "bad id",
                result.getResponse().getHeader("X-Correlation-ID"));
    }

    @Test
    void asyncRedispatchKeepsId() throws Exception {
        MvcResult started =
                mvc.perform(get("/api/async")
                        .header("X-Correlation-ID", "req-async12345"))
                        .andExpect(request().asyncStarted())
                        .andReturn();

        mvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Correlation-ID", "req-async12345"))
                .andExpect(jsonPath("$.correlationId")
                        .value("req-async12345"));
    }

    @Test
    void expectedErrorStillHasCorrelationHeader()
            throws Exception {
        mvc.perform(get("/api/fail"))
                .andExpect(status().isBadRequest())
                .andExpect(header().exists("X-Correlation-ID"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

MockMvc xác nhận HTTP request qua MVC/filter setup, không phải bằng chứng rằng event-loop latency hay error dispatch thật trên mọi Servlet container đều chính xác. Khi kiểm tra async thực tế, nên thêm integration test với RANDOM_PORT và HTTP client; test timeout/cancellation riêng.

### 9.1. Không test một duration cố định

Latency chịu ảnh hưởng CPU, GC, JIT, thread scheduling và hệ điều hành. Unit test không nên đòi "GET /api/hello luôn <10ms" ở mọi CI runner, vì dễ flaky. Có thể kiểm tra rằng mốc start được đặt một lần, interceptor không ghi thời gian âm, metric được đăng ký đúng name và route được chuẩn hóa.

Dùng load test/integration test trên môi trường có cấu hình cố định để đánh giá P95/P99 hoặc SLO. Trong production, quan sát xu hướng theo thời gian thay vì một request riêng lẻ.

## 10. Micrometer Observation và http.server.requests trong Spring Boot

Trong Spring Boot 3.3, Actuator hỗ trợ tự động instrumentation HTTP server requests của Spring MVC và Spring WebFlux. Tên observation/meter logic mặc định là **http.server.requests**; có thể đổi bằng management.observations.http.server.requests.name. Metrics registry/exporter quyết định cách tên xuất hiện ở hệ thống như Prometheus.

Điểm mạnh so với Timer viết tay:

- Quan sát được nhiều phần của HTTP exchange theo hạ tầng framework.
- Có low-cardinality tags như method, status, outcome và route template tùy instrumentation.
- Áp dụng cùng mô hình cho MVC và WebFlux.
- Tích hợp thành metrics, và có thể thành tracing spans khi có tracing bridge.
- Tránh xây một phép đo khác mỗi lần đội phát triển thêm handler.
- Có các điểm mở rộng observation conventions để bổ sung metadata an toàn.

Với project đã có Actuator và được expose metrics endpoint, thử:

~~~bash
curl -i http://localhost:8080/actuator/metrics/http.server.requests
~~~

Đường này cần đúng management port/base-path và chính sách bảo mật. Nếu chưa có HTTP request nào tạo metric, endpoint có thể không trả dữ liệu cho tên đó. Không mở metrics ra Internet chỉ để debug.

### 10.1. Hướng dẫn cấu hình

Ví dụ application.yml:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics

  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

Đây là cấu hình **tùy chọn** cho histogram trên http.server.requests ở phiên bản Boot/Micrometer hỗ trợ; có thể làm tăng số time series và chi phí lưu trữ. Trước khi bật rộng trên production, kiểm tra số lượng route/tags, metrics backend và nhu cầu percentile aggregation.

Để xuất Prometheus cần thêm registry tương ứng, ví dụ dependency micrometer-registry-prometheus và cấu hình endpoint/monitoring phù hợp. Không khẳng định Actuator starter mặc định sẽ tự có /actuator/prometheus khi chưa cài registry và expose endpoint.

### 10.2. Low-cardinality tags so với high-cardinality context

Nên dùng:
- HTTP method: GET/POST/PUT...
- Status: 200/404/500...
- Route template: /api/orders/{id}, không phải /api/orders/42.
- Outcome hoặc nhóm error code hữu hạn nếu có catalog.

Không dùng làm metric tags:
- correlationId/traceId/spanId.
- Raw full URI, path chứa ID ngẫu nhiên, query string.
- Email, userId, orderId, API key, JWT, session ID.
- Exception message có giá trị tùy theo input.

Micrometer Observation phân biệt low-cardinality và high-cardinality key-values. High-cardinality metadata có thể phù hợp với traces khi đã kiểm soát bảo mật, **không** phù hợp với metric tags có số giá trị không giới hạn.

### 10.3. Log duration và metric duration không trùng phạm vi

Một dòng log từ HandlerInterceptor có thể báo 12 ms, trong khi http.server.requests báo thời gian hơi khác. Khác biệt có thể hợp lệ vì điểm bắt đầu/kết thúc, thứ tự filter, async dispatch hoặc ghi response body. Cần ghi rõ semantic của mỗi số, tránh buộc chúng luôn bằng nhau và gắn nhãn "lỗi đo" khi instrumentation hoạt động đúng.

## 11. Spring MVC: truyền correlation ID sang HTTP client

Filter đã đặt ID vào Servlet request attribute và MDC của thread đang xử lý. Nếu controller gọi service downstream bằng RestClient/RestTemplate, có thể dùng interceptor của HTTP client để đặt X-Correlation-ID.

Với Spring Boot 3.3, RestClient.Builder được Boot auto-configure có thể được inject làm builder. Ví dụ snippet trong một @Configuration:

~~~java
@Bean
RestClient partnerRestClient(RestClient.Builder builder) {
    return builder.requestInterceptor((request, body, execution) -> {
        RequestAttributes attributes =
                RequestContextHolder.getRequestAttributes();

        if (attributes instanceof ServletRequestAttributes servlet) {
            Object value = servlet.getRequest()
                    .getAttribute(CorrelationIdFilter.ATTRIBUTE);

            if (value instanceof String id) {
                request.getHeaders().set(
                        CorrelationIdFilter.HEADER, id);
            }
        }

        return execution.execute(request, body);
    }).build();
}
~~~

Đây là @Bean method minh họa, cần import org.springframework.web.client.RestClient, org.springframework.web.context.request.RequestAttributes, RequestContextHolder, ServletRequestAttributes và @Bean. Nó có nghĩa khi client được gọi trong thread mang request attributes phù hợp.

**Không mặc định hoạt động với @Async, CompletableFuture.supplyAsync, scheduled jobs hoặc arbitrary executor threads**: RequestContextHolder thường dùng ThreadLocal và không tự đi theo mọi thread. Khi code chuyển thread, truyền ID như một method argument/immutable context hoặc dùng TaskDecorator/context propagation của executor được cấu hình.

### 11.1. Dùng TaskDecorator cho executor do Spring quản lý

Nếu sử dụng ThreadPoolTaskExecutor mà ứng dụng tự cấu hình, có thể cài TaskDecorator để mang MDC của thread tại thời điểm submit task. Pseudocode an toàn về idea:

~~~java
TaskDecorator decorator = task -> {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();

        try {
            if (captured == null) MDC.clear();
            else MDC.setContextMap(captured);

            task.run();
        } finally {
            if (previous == null) MDC.clear();
            else MDC.setContextMap(previous);
        }
    };
};
~~~

Đây là snippet, cần import java.util.Map, org.slf4j.MDC và org.springframework.core.task.TaskDecorator, sau đó đặt decorator vào đúng executor bằng setTaskDecorator. Nó **chỉ** tác động những task thực sự đi qua executor đó. Không làm CompletableFuture commonPool, Reactor scheduler hay mọi thư viện ngoài tự động inherit MDC.

Lưu ý sao chép thông tin vừa đủ, cleanup trong finally và không để tasks sống rất lâu giữ reference tới request objects. Nếu đã có Micrometer Context Propagation/Tracing, ưu tiên cơ chế chuẩn thay vì tự viết decorator trùng lặp hoặc gây xung đột.

### 11.2. Với WebClient dùng trong Spring MVC

Một MVC application có thể sử dụng WebClient, nhưng không có nghĩa server đổi sang WebFlux. Khi WebClient hoạt động theo Reactor pipeline, MDC/RequestContextHolder không tự động đúng ở từng callback thread. Có thể trích correlation ID khi còn ở Servlet thread rồi truyền vào WebClient request header một cách tường minh; nếu cần propagation sâu, dùng Reactor Context và instrumentation được hỗ trợ.

## 12. Spring WebFlux: WebFilter + Reactor Context + doFinally

Với WebFlux reactive server, Servlet Filter và MVC HandlerInterceptor **không phải** điểm mở rộng mặc định trên Reactor Netty. Spring WebFlux dùng WebFilter, ServerWebExchange và reactive chain.

Một WebFilter có thể:

1. Lấy hoặc tạo correlation ID.
2. Lưu trong ServerWebExchange attributes.
3. Đặt X-Correlation-ID trên response.
4. Đưa ID vào Reactor Context cho các reactive operations.
5. Đo duration từ lúc subscription bắt đầu cho đến khi Publisher hoàn tất, lỗi hoặc bị hủy.
6. Log status/route khi có thông tin.
7. Không block event-loop threads và không dựa vào ThreadLocal MDC truyền qua mọi callback.

### 12.1. Reactor Context không giống MDC

MDC thuộc ThreadLocal (với SLF4J phổ biến). Một reactive pipeline có thể chuyển event-loop thread hoặc scheduler; đặt MDC bằng try/finally quanh lệnh trả Mono không giữ ID cho mọi operator. Reactor Context gắn theo subscription và có thể truy cập bằng Mono.deferContextual hoặc Flux.deferContextual trong pipeline.

**Đừng gọi .subscribe() trong WebFilter** để bắt đầu đo, vì như vậy có thể tách công việc khỏi HTTP exchange và làm sai cancellation/errors. Trả về Mono<Void> do chain cung cấp, bổ sung operators và để runtime subscribe.

### 12.2. Ví dụ WebFlux Java 17+

Trong **một project Spring Boot WebFlux riêng** với spring-boot-starter-webflux và spring-boot-starter-test, tạo class main trong package dev.example.correlationrx:

~~~java
package dev.example.correlationrx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveCorrelationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveCorrelationApplication.class, args);
    }
}
~~~

Đây là file ReactiveCorrelationApplication.java. Tạo tiếp src/main/java/dev/example/correlationrx/RequestContextWebFilter.java:

~~~java
package dev.example.correlationrx;

import java.util.UUID;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestContextWebFilter implements WebFilter {

    private static final Logger LOG =
            LoggerFactory.getLogger(RequestContextWebFilter.class);

    public static final String HEADER = "X-Correlation-ID";
    public static final String KEY = "correlationId";

    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{8,64}");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return Mono.defer(() -> {
            String incoming = exchange.getRequest()
                    .getHeaders().getFirst(HEADER);

            String id = incoming != null
                    && SAFE.matcher(incoming).matches()
                    ? incoming
                    : UUID.randomUUID().toString();

            long startNanos = System.nanoTime();

            exchange.getAttributes().put(KEY, id);
            exchange.getResponse().getHeaders().set(HEADER, id);

            return chain.filter(exchange)
                    .doFinally(signal -> {
                        long nanos = System.nanoTime() - startNanos;
                        double durationMs = nanos / 1_000_000.0;

                        Object mapping = exchange.getAttribute(
                                HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

                        String route = mapping == null
                                ? "UNMAPPED"
                                : mapping.toString();

                        HttpStatusCode status = exchange
                                .getResponse().getStatusCode();

                        LOG.info(
                                "rx_request method={} route={} status={} "
                                + "durationMs={} correlationId={} signal={}",
                                exchange.getRequest().getMethod(),
                                route,
                                status == null
                                        ? "UNSET"
                                        : status.value(),
                                durationMs,
                                id,
                                signal);
                    })
                    .contextWrite(context -> context.put(KEY, id));
        });
    }
}
~~~

Các tính chất:

- Mono.defer đưa thao tác lấy ID/đặt mốc thời gian về giai đoạn subscribe.
- ServerWebExchange.attributes giữ ID cho handler và error handler thuộc cùng exchange.
- contextWrite đặt ID trong Reactor Context của downstream reactive chain.
- doFinally chạy khi chain phát tín hiệu hoàn tất, lỗi hoặc cancellation; signal giúp phân biệt COMPLETE, ERROR, CANCEL.
- Dùng route template từ HandlerMapping nếu có, thay vì raw URI có high cardinality.
- Không ghi status=200 khi status còn null.
- Đây là **thời gian của Publisher/handler chain mà WebFilter bọc**, không thể mặc định đồng nhất với client end-to-end network latency hay mọi thời điểm socket được flush.
- Nếu có một lỗi ngoài WebFilter hoặc connection đóng trước khi xử lý được, không bảo đảm response header/body đã được gửi cho client; logs/metrics vẫn cần error handling thích hợp.

### 12.3. Reactive controller

Tạo src/main/java/dev/example/correlationrx/ReactiveDemoController.java:

~~~java
package dev.example.correlationrx;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class ReactiveDemoController {

    @GetMapping("/api/hello")
    public Mono<Map<String, String>> hello(
            ServerWebExchange exchange) {

        String id = exchange.getAttribute(
                RequestContextWebFilter.KEY);

        return Mono.just(Map.of(
                "message", "hello",
                "correlationId", id == null ? "missing" : id));
    }

    @GetMapping("/api/reactor-context")
    public Mono<Map<String, String>> context() {
        return Mono.deferContextual(view -> {
            String id = view.getOrDefault(
                    RequestContextWebFilter.KEY, "missing");

            return Mono.just(Map.of("correlationId", id));
        });
    }
}
~~~

Hai endpoints cho phép thấy ID từ exchange attribute và từ Reactor Context. Không dùng block()/subscribe() trong controller. WebFlux sẽ subscribe Publisher và serialize JSON.

Chạy project WebFlux bằng ./gradlew bootRun; thử:

~~~bash
curl -i -H "X-Correlation-ID: req-rx123456" \
  http://localhost:8080/api/hello

curl -i -H "X-Correlation-ID: req-rx123456" \
  http://localhost:8080/api/reactor-context
~~~

Khi chạy độc lập trên port 8080, response đầu chứa message=hello, correlationId=req-rx123456, response thứ hai chứa correlationId=req-rx123456. Header X-Correlation-ID có cùng giá trị, theo quy tắc demo. Không chạy đồng thời project MVC ví dụ trước và WebFlux này trên cùng port nếu chưa đổi server.port cho một project.

### 12.4. WebTestClient

Tạo src/test/java/dev/example/correlationrx/ReactiveCorrelationTest.java:

~~~java
package dev.example.correlationrx;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ReactiveCorrelationTest {

    @Autowired
    WebTestClient client;

    @Test
    void headerAndBodyUseSameId() {
        client.get().uri("/api/hello")
                .header("X-Correlation-ID", "req-rx123456")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-Correlation-ID", "req-rx123456")
                .expectBody()
                .jsonPath("$.correlationId")
                .isEqualTo("req-rx123456");
    }

    @Test
    void reactorContextHasRequestId() {
        client.get().uri("/api/reactor-context")
                .header("X-Correlation-ID", "req-ctx123456")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.correlationId")
                .isEqualTo("req-ctx123456");
    }
}
~~~

Test dùng WebFlux mock web environment và Spring Boot test auto-configuration, không tự chứng minh Reactor Netty network behavior. Với project có authentication, WebFilter khác hoặc ngoại lệ, cần bổ sung test config/integration phù hợp. Để kiểm tra socket disconnect, network timeout hoặc streaming cancellation thực, dùng RANDOM_PORT và một HTTP client thực.

## 13. WebFlux: truyền correlation ID qua WebClient

Để gọi downstream từ pipeline WebFlux, dùng một ExchangeFilterFunction trên WebClient và đọc Reactor Context ngay tại reactive subscription.

Snippet bên trong @Configuration:

~~~java
@Bean
WebClient downstreamClient(WebClient.Builder builder) {
    return builder.filter((request, next) ->
            Mono.deferContextual(context -> {
                String id = context.getOrDefault(
                        RequestContextWebFilter.KEY, "");

                ClientRequest.Builder changed =
                        ClientRequest.from(request);

                if (!id.isBlank()) {
                    changed.headers(headers ->
                            headers.set("X-Correlation-ID", id));
                }

                return next.exchange(changed.build());
            }))
            .build();
}
~~~

Đây là **method snippet**, cần imports WebClient, ClientRequest, Mono, Bean và class configuration phù hợp. Inject WebClient.Builder do Boot cung cấp để giữ phần lớn customizations của Boot khi khả dụng.

Một điều cần lưu ý là **context chỉ đi theo reactive chain được compose đúng**. Nếu controller gọi một Publisher rồi tự subscribe detached, context có thể bị mất hoặc vòng đời request không còn kiểm soát được. Hãy trả Publisher từ controller hoặc compose với flatMap/then; không dùng một side effect fire-and-forget để “truyền header”.

Trace context W3C nên được instrumentation của Micrometer/OpenTelemetry truyền riêng. Không tự gắn traceparent bằng cách lấy correlationId; chúng có định dạng và nghĩa khác nhau.

## 14. Các vấn đề async, lỗi và response streaming

### 14.1. Servlet async

Nếu controller trả Callable, DeferredResult hoặc ResponseBodyEmitter, phần việc có thể tiếp diễn sau khi Servlet Filter REQUEST dispatch đã thoát. Vì vậy:

- Không dùng filter finally của REQUEST dispatch làm thời điểm chắc chắn response đã hoàn tất.
- Request attribute là chỗ lưu ID và mốc bắt đầu tốt hơn một ThreadLocal thuần.
- MDC phải được khôi phục ở từng thread/dispatch liên quan khi cần log.
- HandlerInterceptor có thể nhận preHandle nhiều lần khi redispatch; đừng reset mốc.
- Timeout, connection close và một số network errors có thể bỏ qua afterCompletion.
- Nên dùng framework HTTP observations hoặc async callbacks chuyên biệt nếu yêu cầu đo hoàn chỉnh.

### 14.2. WebFlux streaming

Nếu controller trả Flux hoặc SSE stream kéo dài, duration của WebFilter có thể đo đến khi Publisher complete/error/cancel, chứ không phải chỉ đến phần tử đầu tiên. Một stream sống hàng giờ sẽ làm thời lượng rất lớn và ảnh hưởng percentile distribution; cân nhắc một nhóm metric riêng cho streaming endpoints.

Khi response đã committed, lỗi muộn không phải lúc nào cũng đổi được HTTP status hoặc thêm một JSON error body. Đừng đặt correlation header sau khi response bắt đầu stream; đặt trước chain hoặc dùng beforeCommit phù hợp.

### 14.3. Error dispatch và /error

Filter đăng ký ERROR dispatcher có cơ hội khôi phục MDC/ID khi container chuyển sang /error. Tuy nhiên cơ chế error handling có thể tạo response từ BasicErrorController, Spring Security hoặc Servlet container mà không đi qua MVC handler bạn dự định. Cần test status và header thực tế. Một correlationId có trong request attribute không tự bảo đảm mọi error body đều có trường correlationId.

Trong WebFlux, lỗi từ WebFilter, annotated controller và WebExceptionHandler có đường xử lý khác nhau. Một WebFilter đo duration có thể nhận signal ERROR rồi error handler ở tầng ngoài mới quyết định response. Vì vậy nếu status chưa có tại doFinally, log UNSET và dựa vào server observation/error handler để biết kết quả cuối.

### 14.4. Client disconnect

Khi client đóng kết nối giữa chừng, server có thể log I/O exception hoặc reactive CANCEL. Client không nhất thiết nhận được status/header, ngay cả khi server đã gắn header trong response object. Do đó cần logs/tracing với correlation ID nội bộ để điều tra. Không xem “server đã setHeader” là bằng chứng header đã đến client.

## 15. Bảo mật, CORS và log hygiene

Một thiết kế dễ dùng cho debugging có thể trở thành lỗ hổng nếu thiếu kiểm soát.

- Không log Authorization, Cookie session, password hoặc raw body chỉ để tìm ID.
- Không tạo ID từ email/userId/tenantId vì dễ lộ và có thể bị suy đoán.
- Validate incoming correlation header; tránh CR/LF log injection và header dài quá mức.
- Đảm bảo ID do client gửi không trở thành bằng chứng xác thực/quyền truy cập.
- Nếu cần hỗ trợ liên hệ, client chỉ cần gửi correlation ID và thời điểm; không yêu cầu chia sẻ access token.
- Không đưa ID làm metric label hoặc span attribute lặp vô hạn khi telemetry backend không chịu tải.
- Phân quyền truy cập logs và retention phù hợp.
- Không dùng raw URL kèm query nhạy cảm trong logs/metrics.
- Nếu dùng OpenTelemetry/Micrometer, tránh tự tạo thêm trace context xung đột.
- Khi retry hoặc chạy batch jobs, quy định ID mới hay tái sử dụng theo transaction scope.
- Thêm service.name, environment và timestamp vào structured logs để tìm ID không bị lẫn giữa nhiều service.

### 15.1. CORS expose X-Correlation-ID khi frontend cần đọc

Với browser chạy cross-origin, JavaScript có thể không đọc được custom response header nếu CORS không expose. Có thể thiết lập Access-Control-Expose-Headers: X-Correlation-ID theo CORS policy của Spring Security/gateway. Không hiểu nhầm việc header có trong network response với việc browser script chắc chắn đọc được.

Không mở permissive CORS wildcard với credentials chỉ vì muốn frontend lấy correlation ID. Cần cấu hình origin/credentials/exposed headers theo chính sách bảo mật.

### 15.2. Structured logging tốt hơn ghép chuỗi thủ công

Một log concept:

~~~json
{
  "timestamp": "2026-11-07T12:00:00Z",
  "level": "INFO",
  "service": "orders-api",
  "httpMethod": "GET",
  "route": "/api/orders/{id}",
  "httpStatus": 200,
  "durationMs": 24.7,
  "correlationId": "req-order12345",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "message": "HTTP request completed"
}
~~~

Đây là log minh họa, không phải dữ liệu hệ thống thật. Tránh log raw order ID hoặc query string nếu không có lý do/kiểm soát. Dùng fields riêng để lọc, không yêu cầu nhân viên parse tự do từ message.

## 16. Phân biệt khi nào cần tự viết Timer

Tự viết Timer là hợp lý nếu bạn muốn đo **một operation nghiệp vụ** mà built-in HTTP instrumentation không biết, ví dụ reserveStock, calculateShipping hoặc một bước domain transaction. Khi đó đặt tên metric mới, chẳng hạn order.reservation.duration, và gắn các tags hữu hạn như outcome=success/failure.

Đối với HTTP server duration, Spring Boot đã có http.server.requests. Trước khi tạo một Filter đo và publish metrics mới, hãy kiểm tra mục tiêu:

| Mục đích | Phương pháp ưu tiên |
|---|---|
| Tìm tất cả log của một request | Correlation ID + logs + trace |
| Đo P95 server HTTP latency | Built-in http.server.requests |
| Đo một controller/MVC handler cụ thể để debug | HandlerInterceptor với scope rõ, hoặc observation tùy biến |
| Đo thời gian SQL query | Database instrumentation / query timer |
| Đo outbound WebClient duration | Built-in http.client.requests / client observation |
| Đo business step | Custom Observation/Timer với tên/tags riêng |
| Theo dõi request multi-service | Distributed tracing + correlation |
| Đo frontend end-to-end | Browser/mobile client telemetry, không thể suy ra chỉ từ server |

### 16.1. Micrometer Timer mẫu cho một bước nghiệp vụ

Khi thật sự cần metric riêng:

~~~java
public String runBusinessOperation(MeterRegistry registry) {
    Timer.Sample sample = Timer.start(registry);

    String outcome = "success";
    try {
        return calculateResult();
    } catch (RuntimeException ex) {
        outcome = "failure";
        throw ex;
    } finally {
        sample.stop(Timer.builder("business.operation.duration")
                .tag("outcome", outcome)
                .register(registry));
    }
}
~~~

Đây là **snippet** cần imports io.micrometer.core.instrument.MeterRegistry, Timer và định nghĩa calculateResult(). Nó đo thời gian method đồng bộ. Nếu calculateResult() trả Mono/Flux, đặt sample.stop trong finally của method chỉ đo thời gian **tạo Publisher**, không đo khi publisher thực sự chạy. Với reactive method, nên tạo Observation/Timer trong Mono.defer và stop khi Publisher hoàn tất/error/cancel.

Không gắn correlationId vào Timer.builder(...).tag(...), và không dùng mã user/product/transaction làm tag.

### 16.2. Thận trọng với status khi có exception

Một Timer ở domain layer có thể phân loại outcome=failed khi exception xảy ra, nhưng HTTP controller có thể xử lý exception thành 409/404. Kết quả business operation và HTTP response status không đồng nhất 1:1; metrics nên có định nghĩa rõ thay vì gán mọi exception thành server 500.

## 17. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Response có ID nhưng log không có | MDC không được gắn trước logging, thread khác, pattern thiếu | Filter order, MDC propagation, logging config |
| Một request có hai correlation IDs | Filter/gateway tạo mới tại mỗi dispatch/hop | Request attribute, trusted ingress policy |
| Async endpoint log mất correlationId | Callable/@Async chạy trên thread khác | TaskDecorator, tracing/context propagation |
| Request bình thường có duration, async timeout không có | afterCompletion không được gọi khi không redispatch | Dùng async callbacks hoặc Boot observation |
| Một request được đếm 2 lần trong custom metric | Tính tại từng REQUEST/ASYNC dispatch | Dùng start attr + completion once hoặc built-in observation |
| P95 tăng nhưng log handler ngắn | Latency nằm ngoài handler, downstream, queue, network | So sánh HTTP server/client observations và traces |
| Filter log báo 200 nhưng client nhận 500 | Log status quá sớm trước error dispatch | Ghi tại completion boundary thích hợp |
| CORS frontend không đọc được ID | Không expose custom header | Access-Control-Expose-Headers |
| WebFlux mất ID khi publishOn | Dựa vào MDC ThreadLocal | Reactor Context + context propagation |
| WebFlux dừng stream nhưng không thấy COMPLETE | Publisher bị cancel/error | doFinally signal, network logs |
| Metrics tăng số series đột biến | Tag chứa raw path/ID | Route templates, low-cardinality tags |
| 401/403 không có JSON lỗi mong muốn | Spring Security xử lý trước MVC advice | AuthenticationEntryPoint/AccessDeniedHandler |
| /error không có body correlationId | Container error handling khác advice | ErrorController/ErrorAttributes và ERROR dispatch |
| Client có ID nhưng downstream không có | HTTP client không gắn header/context | RestClient/WebClient instrumentation/interceptors |
| Có traceId nhưng không có X-Correlation-ID | Hệ thống chỉ bật tracing, chưa khai báo header contract | Thiết kế hợp đồng riêng hoặc chủ động dùng traceId |
| Latency trong log luôn 0ms | Đã làm tròn sang millisecond số nguyên | Log double hoặc nanoseconds |
| Duration âm/bất thường | Dùng wall clock hoặc kết hợp hai máy | System.nanoTime trong một JVM, đúng start/end |
| HTTP metric thiếu | Chưa có Actuator/registry, endpoint chưa được gọi/expose | Dependencies, actuator exposure, metrics configuration |
| Tạo filter hai lần | Vừa @Component vừa tạo FilterRegistrationBean khác | Kiểm tra bean registration và order |
| Client tấn công bằng ID rất dài | Header không được giới hạn | Validate length/charset tại ingress/filter |

## 18. Checklist trước production

- [ ] Đã chọn một tên correlation header và chính sách trusted ingress.
- [ ] Có giới hạn độ dài, ký tự và header duplicates; không nhận giá trị chứa CR/LF.
- [ ] ID sinh mới khi thiếu/không hợp lệ, không phụ thuộc PII.
- [ ] ID lưu trong request attribute hoặc ServerWebExchange attributes phù hợp.
- [ ] Header trả về trước khi response committed.
- [ ] MDC chỉ được dùng trong thread hợp lệ, có cleanup/restoration.
- [ ] Async dispatch, @Async, CompletableFuture và reactor schedulers được kiểm thử riêng.
- [ ] Đã xác định việc propagate sang RestClient, RestTemplate, WebClient hoặc message broker.
- [ ] W3C traceparent được instrumentation quản lý khi dùng tracing.
- [ ] Có log structured fields: correlationId, traceId, route, method, status, duration.
- [ ] Không đặt correlationId/traceId/raw URI làm metric tag high cardinality.
- [ ] HTTP server latency dùng http.server.requests khi Actuator hoạt động, tránh đếm đôi.
- [ ] Đo P95/P99 có histogram/SLI đúng scope và chi phí chấp nhận được.
- [ ] Các đường lỗi 400/401/403/404/500, /error và gateway có correlation policy.
- [ ] Test async completion, timeout, disconnect, cancellation và streaming.
- [ ] Với WebFlux, contextWrite/deferContextual có test và không tự subscribe tách nhánh.
- [ ] Với MVC, filter dispatcher types và shouldNotFilter... được kiểm tra đồng bộ.
- [ ] CORS expose header khi browser frontend thật sự cần.
- [ ] Không log secrets/rejected values; có retention và quyền truy cập logs.
- [ ] Không dùng correlation ID làm idempotency key hoặc security principal.
- [ ] Documentation mô tả mỗi duration metric đo đúng khoảng nào.

## 19. Câu hỏi tự kiểm tra

**Câu 1. Vì sao không dùng System.currentTimeMillis để đo latency?**  
Vì wall-clock có thể thay đổi bởi chỉnh giờ/NTP, còn System.nanoTime thích hợp tính elapsed duration trong cùng JVM.

**Câu 2. OncePerRequestFilter bảo đảm chạy đúng một lần trong toàn vòng đời async không?**  
Không. Nó xử lý theo request dispatch và thread; ASYNC/ERROR phụ thuộc flags và Servlet registration.

**Câu 3. Vì sao preHandle có thể được gọi hai lần với một Callable?**  
Vì MVC có thể redispatch khi kết quả async hoàn tất; cần giữ mốc bắt đầu trong request attribute.

**Câu 4. HandlerInterceptor đo toàn request khi client disconnect không?**  
Không bảo đảm. afterCompletion có thể không chạy khi timeout/network error không có redispatch; dùng observations hoặc async callbacks phù hợp.

**Câu 5. MDC có đi theo WebFlux Reactor Context không?**  
Không tự động. Reactor Context và ThreadLocal MDC là hai cơ chế khác nhau; cần bridge/instrumentation phù hợp.

**Câu 6. Có nên tag metric với correlationId để tìm request chậm không?**  
Không. Cardinality rất cao. Tra cứu request riêng trong logs/traces; metrics dùng low-cardinality dimensions.

**Câu 7. Trace ID và correlation ID có luôn giống nhau không?**  
Không. Có thể thống nhất có chủ đích nhưng khác định dạng, phạm vi và nguồn tạo.

**Câu 8. Filter response header có đủ bao phủ lỗi Spring Security và gateway không?**  
Không. Filter có thể bao phủ một số security paths nếu order/mapping phù hợp; gateway trả lỗi trước khi chuyển request vào backend phải tự gắn ID.

**Câu 9. Vì sao doFinally trên WebFilter cần xét CANCEL?**  
Vì client disconnect hoặc cancellation làm Publisher không hoàn tất bình thường, và cần log sự kiện thay vì báo thành công.

**Câu 10. Nếu muốn đo riêng một business operation trong Mono, có nên stop Timer ngay khi method trả Mono không?**  
Không. Mono thường chưa chạy khi được tạo; phải đo bên trong reactive subscription và stop tại completion/error/cancel.

## 20. Tổng kết

**Correlation ID** giúp nối các log và những lời gọi thuộc cùng một tương tác; **request duration** giúp đánh giá độ trễ. Trong Spring Boot, đặt correlation ID đủ sớm tại Servlet Filter hoặc WebFlux WebFilter, truyền ID theo context và trả response header theo một hợp đồng có kiểm soát.

Ở Servlet MVC, OncePerRequestFilter có thể gắn ID/MDC trước controller, còn HandlerInterceptor giúp đọc route metadata và ghi nhận thời gian handler. Tuy nhiên ASYNC/ERROR dispatch, timeout và network errors là những ranh giới làm phép đo tự viết dễ sai: cần thiết kế callback và ownership rõ, không tự coi Filter finally hay afterCompletion luôn là kết thúc HTTP request.

Ở WebFlux, dùng ServerWebExchange attributes, Reactor Context và các operators như defer/contextWrite/doFinally; không dựa vào ThreadLocal hoặc .subscribe() thủ công để truyền metadata. Với distributed tracing, dùng Micrometer/OpenTelemetry truyền W3C trace context thay vì tự tạo traceparent.

Để đo SLO HTTP server trên production, ưu tiên **Micrometer http.server.requests** đã được Spring Boot Actuator instrument, kết hợp structured logging và distributed traces. Giữ high-cardinality IDs ở logs/traces, còn metrics chỉ dùng tags hữu hạn. Khi có quy tắc rõ “ID do ai cấp, đi theo đường nào, duration đo từ đâu đến đâu và ai kết thúc phép đo”, hệ thống dễ truy vết và đáng tin hơn khi chịu tải, chạy bất đồng bộ hoặc xảy ra lỗi.

## 21. Tài liệu tham khảo

- Spring Framework 6.1 — OncePerRequestFilter Javadoc: https://docs.spring.io/spring-framework/docs/6.1.9/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework — AsyncHandlerInterceptor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/AsyncHandlerInterceptor.html
- Spring Framework — Asynchronous Requests in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — WebFlux WebHandler API & WebFilter: https://docs.spring.io/spring-framework/reference/web/webflux-web-handler-api.html
- Spring Framework — WebClient Context: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-context.html
- Spring Boot 3.3 — Metrics and HTTP server observations: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot — Observability: https://docs.spring.io/spring-boot/reference/actuator/observability.html
- Spring Boot — Distributed Tracing: https://docs.spring.io/spring-boot/reference/actuator/tracing.html
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- Micrometer — Observation Concepts: https://docs.micrometer.io/micrometer/reference/observation/introduction.html
- Project Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html

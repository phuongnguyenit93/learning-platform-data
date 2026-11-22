# Filter của Servlet, HandlerInterceptor của MVC và WebFilter của WebFlux

## 1. Mục tiêu bài học

Trong Spring Boot, cùng một yêu cầu như đo thời gian HTTP, cấp correlation ID, thay đổi header hoặc kiểm tra một request có thể được thực hiện bằng nhiều cơ chế. **Servlet Filter**, **HandlerInterceptor của Spring MVC** và **WebFilter của Spring WebFlux** không phải ba tên thay thế cho cùng một thứ: chúng nằm ở **những giai đoạn khác nhau của request lifecycle** và chạy trên **những mô hình thực thi khác nhau**.

Bài thuộc nhóm **Bộ lọc và interceptor**. Sau bài này, bạn sẽ:

1. Hiểu vai trò, giai đoạn và API của **jakarta.servlet.Filter**, **org.springframework.web.servlet.HandlerInterceptor** và **org.springframework.web.server.WebFilter**.
2. Vẽ được thứ tự before/after khi có nhiều Filter và interceptor.
3. Biết khi nào dùng Servlet Filter cho HTTP-level concerns, HandlerInterceptor cho handler-level concerns, WebFilter cho reactive HTTP pipeline.
4. Kiểm soát registration, order, URL patterns, async/error dispatch, short-circuit và exception.
5. Không đặt authorization sai chỗ hoặc đăng ký filter hai lần khi dùng Spring Security.
6. Tránh block Netty event loop, mất reactive context, đọc body hai lần và sửa response đã commit.
7. Chạy hai dự án **Java 17 + Spring Boot 3.5** tách biệt: một Spring MVC với Filter + Interceptor và một WebFlux với WebFilter.
8. Viết test MockMvc và WebTestClient để xác nhận phạm vi thực thi.

Ví dụ dùng **Spring Boot 3.5.x**, Spring Framework **6.2**, Java **17+** và Servlet API thuộc **jakarta.servlet**. Trên Spring Boot 2.x trước đây dùng **javax.servlet**; không thể copy trực tiếp những import đó vào Boot 3.x.

## 2. So sánh ba thành phần

| Tiêu chí | Servlet Filter | MVC HandlerInterceptor | WebFlux WebFilter |
|---|---|---|---|
| Interface | **jakarta.servlet.Filter** | **HandlerInterceptor** | **WebFilter** |
| Stack | Servlet, thường Tomcat | Spring MVC, Servlet stack | Reactive WebFlux |
| Vị trí | Servlet container FilterChain, trước Servlet | MVC HandlerExecutionChain, sau HandlerMapping | Reactive WebHandler chain |
| Đầu vào | ServletRequest, ServletResponse, FilterChain | HttpServletRequest, HttpServletResponse, handler | ServerWebExchange, WebFilterChain |
| Tiếp tục | **chain.doFilter(req,resp)** | **preHandle trả true** | **chain.filter(exchange)** |
| Chặn | Không gọi chain, tự xử lý response | preHandle trả false và xử lý response | Không gọi chain, trả Mono hoàn tất |
| Sau xử lý | Code sau chain.doFilter/finally | postHandle/afterCompletion | Reactor doFinally, doOnError |
| Thấy handler đã chọn? | Chưa | Có tham số handler, thường HandlerMethod | Không trực tiếp ở tầng WebFilter |
| Scope | URL pattern/dispatcher type | HandlerMapping + include/exclude patterns | WebFlux WebHandler chain |
| Ordering | FilterRegistrationBean.setOrder | InterceptorRegistry.order | @Order hoặc Ordered |
| Async | DispatcherType, asyncSupported | AsyncHandlerInterceptor, redispatch | Mono/Flux completion/cancel |
| Security tích hợp | Spring Security Servlet FilterChain | Không dùng làm lớp authz chính | SecurityWebFilterChain |

**Lựa chọn mặc định:** trong Spring MVC, logic cần xử lý trước khi chọn controller thích hợp với **Servlet Filter**; logic cần biết controller method nào được gọi thích hợp với **HandlerInterceptor**. Trong Spring WebFlux, **WebFilter** là điểm xử lý cross-cutting theo reactive chain. Với xác thực và phân quyền, dùng **Spring Security** của đúng stack.

## 3. Luồng request trong Spring MVC

~~~mermaid
flowchart TD
    A[HTTP client] --> B[Servlet Filter 1 before]
    B --> C[Servlet Filter 2 before]
    C --> D[DispatcherServlet]
    D --> E[HandlerMapping tìm handler]
    E --> F[HandlerInterceptor.preHandle]
    F --> G{true?}
    G -->|Có| H[HandlerAdapter gọi controller]
    H --> I[MessageConverter hoặc View]
    I --> J[postHandle rồi afterCompletion]
    G -->|Không| K[Interceptor tự xử lý response]
    J --> K
    K --> L[Servlet Filter 2 after]
    L --> M[Servlet Filter 1 after]
    M --> N[HTTP response]
~~~

Luồng gọi **đồng bộ, thành công** có thể được diễn giải:

~~~text
Filter A trước
  Filter B trước
    DispatcherServlet
      HandlerMapping chọn handler
      Interceptor 1 preHandle
        Interceptor 2 preHandle
          Controller
        Interceptor 2 postHandle
      Interceptor 1 postHandle
      Interceptor 2 afterCompletion
      Interceptor 1 afterCompletion
  Filter B sau
Filter A sau
~~~

Đây là **sơ đồ khái niệm**, không phải stdout cố định của mọi request. Khi có exception, interceptor trả false, Servlet ASYNC/ERROR redispatch hoặc response streaming, một số callback có thể không chạy ở đúng vị trí như ví dụ.

**Điểm khác biệt quan trọng:** Filter chạy **trước DispatcherServlet**; Interceptor chạy **sau khi HandlerMapping đã chọn handler**. Nếu Spring Security đã từ chối request trong Servlet filter chain, HandlerInterceptor thường không hề được gọi.

## 4. Servlet Filter

Interface **jakarta.servlet.Filter** có phương thức khái niệm:

~~~java
void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException;
~~~

Đây là API minh họa, cần implements Filter hoặc một base class thực tế để thành class chạy được.

### 4.1. Trước, sau, exception và short-circuit

Mẫu xử lý:

~~~java
try {
    // Thực hiện bước trước Servlet.
    chain.doFilter(request, response);
} finally {
    // Cleanup khi lời gọi chain kết thúc.
}
~~~

**chain.doFilter** tiếp tục sang Filter kế tiếp hoặc Servlet. Nếu không gọi chain và tự trả response, request bị short-circuit. Ví dụ trong maintenance mode, có thể trả **503 Service Unavailable**, nhưng controller sẽ không được chạy.

**Không giả định** finally của Filter luôn tương đương “HTTP request hoàn tất tới byte cuối cùng”. Với MVC asynchronous processing, chain có thể trở về trước khi body đã phát xong.

### 4.2. GenericFilterBean và OncePerRequestFilter

- **GenericFilterBean** tích hợp Filter với Spring bean lifecycle.
- **OncePerRequestFilter** giúp xử lý một lần trong request dispatch theo contract của Spring và cung cấp tùy chọn kiểm soát **ASYNC**/**ERROR** dispatch.

Không diễn giải OncePerRequestFilter là “tối đa một lần trong toàn bộ vòng đời request, bất kể redirect, forward hay async”. Một Servlet request có thể có nhiều dispatcher phases và thread, trong khi filter registration còn quy định dispatcher types được phép.

### 4.3. FilterRegistrationBean

Ví dụ đăng ký khi có class MyFilter:

~~~java
@Bean
FilterRegistrationBean<MyFilter> registration() {
    FilterRegistrationBean<MyFilter> bean =
            new FilterRegistrationBean<>(new MyFilter());
    bean.addUrlPatterns("/api/*");
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    bean.setOrder(10);
    return bean;
}
~~~

Đoạn này cần class/import tương ứng và chỉ là ví dụ registration; ứng dụng chạy được nằm ở mục 8.

**Chú ý hai hệ pattern:** Servlet **"/api/*"** không giống cú pháp Spring MVC **"/api/**"**. Chúng có thể phủ các đường dẫn tương tự nhưng không dùng chung parser và không thay thế cho nhau trong mọi tình huống.

Spring Boot 3.5 có thể tự đăng ký Filter bean vào Servlet container. Nếu một Filter vừa **@Component**, vừa được khai báo dưới **FilterRegistrationBean** hoặc thêm trực tiếp vào Spring Security chain, cần kiểm tra nguy cơ chạy **hai lần**. Nếu một Filter bean chỉ dùng trong SecurityFilterChain, cấu hình để không tự auto-register nó ở container, ví dụ registration **setEnabled(false)**.

### 4.4. Filter và Spring Security

Spring Security Servlet stack dùng **DelegatingFilterProxy**, **FilterChainProxy** và các **SecurityFilterChain** bên trong Servlet filter chain. Các tính năng authentication, CSRF, security headers và authorization được xử lý với thứ tự xác định.

Nên cấu hình Spring Security chính thức thay vì tự kiểm tra role theo chuỗi URL ở HandlerInterceptor. Interceptor có thể khác cách Spring Security so khớp path, khiến một biến thể URL có quyền truy cập khác dự kiến.

### 4.5. Lỗi phát sinh trước DispatcherServlet

Nếu custom Servlet Filter ném exception **trước khi** đi vào DispatcherServlet, **@ControllerAdvice** và HandlerExceptionResolver của MVC không tự động xử lý lỗi đó. Lỗi có thể được filter, Servlet container hoặc Boot **/error** giải quyết, tùy cấu hình.

Vì thế muốn chuẩn hóa JSON error cho cả Security, Filter và controller, cần thiết kế hợp đồng lỗi tại đúng tầng.

## 5. HandlerInterceptor của Spring MVC

Interface chính là **org.springframework.web.servlet.HandlerInterceptor**, với ba callback:

~~~java
boolean preHandle(HttpServletRequest request,
                  HttpServletResponse response,
                  Object handler);

void postHandle(HttpServletRequest request,
                HttpServletResponse response,
                Object handler,
                ModelAndView modelAndView);

void afterCompletion(HttpServletRequest request,
                     HttpServletResponse response,
                     Object handler,
                     Exception ex);
~~~

Các chữ ký trên đã rút gọn nullability và throws Exception nhằm giải thích; interface thật có default methods.

### 5.1. preHandle

Chạy sau HandlerMapping và trước handler thực thi:

~~~java
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) {

    request.setAttribute("intercepted", true);
    return true;
}
~~~

Nếu trả **true**, chuỗi tiếp tục. Nếu trả **false**, DispatcherServlet giả định bạn đã xử lý response và không gọi handler. **afterCompletion** của chính interceptor trả false không mặc nhiên được gọi; nếu đã cấp tài nguyên ở preHandle, phải dọn ngay trong nhánh false.

Tham số handler có thể là **HandlerMethod** để truy cập tên class/method:

~~~java
if (handler instanceof HandlerMethod method) {
    String name = method.getMethod().getName();
    // Log/metrics theo handler đã chọn.
}
~~~

Đoạn này cần import HandlerMethod và nằm trong một method đang có biến handler.

### 5.2. postHandle

Với trang MVC server-side render, postHandle có thể chỉnh **ModelAndView** trước view rendering. Với **@ResponseBody/ResponseEntity**, body có thể đã được ghi và response có thể đã commit **trước postHandle**, nên đây không phải nơi đáng tin để đổi JSON body hoặc thêm response header.

Để đổi body REST, xem **ResponseBodyAdvice**. Để thêm header sớm, dùng Servlet Filter, controller hoặc ResponseEntity đúng trường hợp.

### 5.3. afterCompletion

Callback khi DispatcherServlet hoàn tất xử lý và interceptor đã vượt qua preHandle; thích hợp để cleanup và log. Nếu exception làm handler bị gián đoạn, postHandle có thể bị bỏ qua, nhưng afterCompletion vẫn có thể được gọi cho những interceptor đã được áp dụng, theo MVC exception lifecycle.

Với request **Callable**, **DeferredResult** hoặc Servlet async, callback lần dispatch đầu có thể khác. **AsyncHandlerInterceptor.afterConcurrentHandlingStarted** hỗ trợ thời điểm concurrent handling bắt đầu; callback bổ sung của WebAsyncManager giúp theo dõi timeout, error hoặc request ngắt kết nối.

### 5.4. Đăng ký

~~~java
@Configuration
class MvcConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new MyInterceptor())
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/public/**")
                .order(10);
    }
}
~~~

Đây là đoạn minh họa cần class MyInterceptor và imports. **order nhỏ hơn thường chạy trước** trong interceptor chain; phase post/after chạy theo thứ tự ngược ở luồng hoàn tất thông thường. **InterceptorRegistry.order** và **FilterRegistrationBean.setOrder** quản lý hai chain riêng, không lập một thứ tự chung.

Nếu không có HandlerMapping phù hợp, interceptor có thể không chạy. Nhưng request không có controller **có thể** được static resource handler chọn, vì vậy không khẳng định mọi 404 đều bỏ qua interceptor.

## 6. WebFilter của Spring WebFlux

WebFlux có contract:

~~~java
Mono<Void> filter(ServerWebExchange exchange,
                  WebFilterChain chain);
~~~

**ServerWebExchange** chứa request, response, attributes, session/principal API và dữ liệu ngữ cảnh reactive request.

### 6.1. Tiếp tục chuỗi và đo completion

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange,
                         WebFilterChain chain) {
    long start = System.nanoTime();
    return chain.filter(exchange)
            .doFinally(signal -> {
                long elapsedMs =
                        (System.nanoTime() - start) / 1_000_000;
                // Ghi metric, không thực hiện blocking I/O.
            });
}
~~~

Đây là code minh họa nằm trong class implements WebFilter. **chain.filter(exchange)** trả Mono<Void> báo request pipeline hoàn thành.

Một số operator:

| Operator | Vai trò |
|---|---|
| **doOnSubscribe** | Theo dõi subscription |
| **doOnError** | Quan sát lỗi ở pipeline tại vị trí này |
| **doOnSuccess** | Quan sát completion thành công của Mono |
| **doFinally** | Quan sát complete, error hoặc cancel |
| **contextWrite** | Ghi Reactor Context cho các phần xử lý reactive |
| **onErrorResume** | Chuyển lỗi thành publisher thay thế, chỉ khi có policy rõ ràng |

**Không gọi block(), Thread.sleep hoặc JDBC blocking trên Netty event loop**. Reactive WebFilter phải trả về Publisher và không tự subscribe để tách khỏi request lifecycle.

### 6.2. Chặn WebFlux request

Đoạn code ngắn minh họa:

~~~java
exchange.getResponse().setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
return exchange.getResponse().setComplete();
~~~

Nếu không gọi chain.filter(exchange), các filter/handler kế tiếp không thực thi. Dùng chính sách timeout/rate/security ở đúng component; không tự tạo WebFilter làm authorization chính nếu đã có Spring Security.

### 6.3. Per-request state không nên là instance field

WebFilter thường là singleton. Không lưu **currentUser**, **traceId** hoặc **startNanos** của request vào một instance variable mutable. Nhiều request đồng thời sẽ ghi đè dữ liệu.

Dùng **exchange.getAttributes()**, **Reactor Context** hoặc Micrometer context propagation khi thích hợp. Không dựa vào ThreadLocal/MDC thông thường như nguồn dữ liệu đáng tin xuyên qua **publishOn/subscribeOn** vì reactive pipeline có thể chạy trên nhiều thread.

### 6.4. Header và committed response

Đặt header trước khi gọi chain:

~~~java
exchange.getResponse().getHeaders().set("X-Trace-Id", traceId);
return chain.filter(exchange);
~~~

Nếu cần thiết lập sát thời điểm commit, có thể dùng **ServerHttpResponse.beforeCommit** với callback trả Mono<Void>. Đặt header trong **doFinally** thường đã quá muộn vì HTTP response có thể commit.

### 6.5. WebFilter khác HandlerFilterFunction và WebClient filter

- **WebFilter**: server-side cross-cutting filter của toàn WebFlux WebHandler chain.
- **HandlerFilterFunction**: filter ở mức **WebFlux.fn RouterFunction/HandlerFunction**, có phạm vi route chức năng.
- **ExchangeFilterFunction**: filter cho **WebClient outbound** gọi sang server khác, không phải request inbound.

Với Spring Security reactive, **SecurityWebFilterChain** và **ServerHttpSecurity** được dùng để thiết lập authentication/authorization; đừng copy HttpSecurity Servlet vào WebFlux.

### 6.6. WebExceptionHandler

WebFlux có **WebExceptionHandler** bao quanh xử lý trong reactive WebHandler/WebFilter chain. **@RestControllerAdvice** áp dụng vào annotated controller exception handling; không có nghĩa nó sẽ bắt được mọi lỗi ném từ WebFilter trước controller.

Streaming còn có vấn đề response đã commit: nếu lỗi xuất hiện sau khi data đã được flush, không thể đổi status/body thành JSON lỗi mới một cách tùy ý.

## 7. Matrix lựa chọn theo yêu cầu

| Yêu cầu | Cơ chế phù hợp | Ghi chú |
|---|---|---|
| Trace ID cho HTTP MVC ngay khi request vào | Servlet Filter | Có thể đặt header trước DispatcherServlet |
| Log tên controller method của MVC | HandlerInterceptor | Có HandlerMethod sau HandlerMapping |
| Thêm dữ liệu ModelAndView trước HTML render | HandlerInterceptor | postHandle dành cho view |
| Thay đổi JSON REST response | ResponseBodyAdvice | Interceptor postHandle có thể quá muộn |
| CORS, auth, CSRF trong MVC | Spring Security/Servlet Filter integration | Đặt security ở filter chain |
| CORS, auth, CSRF trong WebFlux | SecurityWebFilterChain | Reactive-specific |
| Correlation ID trong WebFlux | WebFilter | Exchange attributes + Reactor Context |
| Đo complete/error/cancel trong WebFlux | WebFilter + doFinally | Đúng theo reactive subscription |
| Middleware cho WebFlux.fn route riêng | HandlerFilterFunction | Phạm vi route chức năng |
| HTTP outbound WebClient request tracing | ExchangeFilterFunction | Không dùng server WebFilter |
| Servlet async completion | AsyncHandlerInterceptor + Filter async mapping | Không chỉ dùng finally đơn giản |

## 8. An toàn và vòng đời body

### 8.1. Body chỉ đọc một lần

Trong Servlet, **ServletInputStream** là stream; nếu Filter tiêu thụ body trước, **@RequestBody** phía controller có thể không còn byte để đọc. **ContentCachingRequestWrapper** cache dữ liệu khi được tiêu thụ, nhưng **không tự biến mọi request thành replayable stream**. Cần dùng wrapper/đọc hợp lý và giới hạn RAM.

Trong WebFlux, request body là **Flux<DataBuffer>**. Nếu WebFilter tự subscribe, join hoặc consume body rồi mới gọi chain.filter, downstream có thể không đọc được body hoặc gặp lỗi bộ nhớ. Khi thật sự cần transform, phải hiểu **ServerHttpRequestDecorator**, DataBuffer ownership và release/discard. Không cache raw body nhạy cảm chỉ để log.

### 8.2. Async, error và cancellation

- **Servlet Filter**: đăng ký DispatcherType.REQUEST/ASYNC/ERROR theo nhu cầu; OncePerRequestFilter có lựa chọn skip async/error dispatch.
- **MVC Interceptor**: callback không giống nhau giữa sync và async; AsyncHandlerInterceptor quản lý pha concurrent.
- **WebFlux WebFilter**: doFinally nhìn thấy completion/error/cancel của Publisher ở vị trí được gắn; reactive pipeline có thể bị hủy nếu client disconnect.

### 8.3. Order và security mismatch

Interceptor không phải lớp phân quyền chính vì matcher của MVC có thể khác rule security. Trong Servlet SecurityFilterChain, filter có thứ tự riêng; custom filter có thể bị gọi hai lần nếu vừa là Spring bean auto-registered vừa được add vào Security chain. Với WebFlux, @Order kiểm soát thứ tự WebFilter, còn WebFilter của Spring Security có các quy tắc riêng.

### 8.4. Logging không được lộ bí mật

Không log Authorization, Cookie, password, access token, raw body, file upload hoặc query string có dữ liệu nhạy cảm một cách mặc định. TraceId nên được server tạo hoặc kiểm tra nếu lấy từ trusted upstream. Dùng Micrometer Observation/Tracing cho observability chuẩn khi phù hợp.

## 9. Ví dụ Spring MVC chạy được: Servlet Filter và HandlerInterceptor

Dự án thứ nhất dùng **Java 17, Spring Boot 3.5.16, spring-boot-starter-web, embedded Tomcat**. Filter tạo traceId sớm, Interceptor xác nhận handler đã chọn, controller trả JSON để đối chiếu.

### 9.1. Cấu trúc

~~~text
mvc-chain-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/mvcdemo/
    │   │   ├── MvcDemoApplication.java
    │   │   ├── TraceFilter.java
    │   │   ├── TraceInterceptor.java
    │   │   ├── MvcConfig.java
    │   │   └── HelloController.java
    │   └── resources/application.yml
    └── test/java/com/example/mvcdemo/
        └── MvcChainTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mvc-chain-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 9.3. MvcDemoApplication.java

~~~java
package com.example.mvcdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcDemoApplication.class, args);
    }
}
~~~

### 9.4. TraceFilter.java

~~~java
package com.example.mvcdemo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

public class TraceFilter extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(TraceFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String traceId = UUID.randomUUID().toString();
        request.setAttribute("traceId", traceId);
        response.setHeader("X-Trace-Id", traceId);

        long start = System.nanoTime();
        log.info("Filter before path={}", request.getRequestURI());

        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMs =
                    (System.nanoTime() - start) / 1_000_000;
            log.info("Filter after status={} durationMs={}",
                    response.getStatus(), elapsedMs);
        }
    }
}
~~~

Class **không dùng @Component** vì sẽ được đăng ký duy nhất qua FilterRegistrationBean. Filter đặt attribute vào Servlet request và header vào response trước downstream. finally giúp đo độ dài lời gọi chain, **không nhất thiết là tổng thời gian HTTP async**.

### 9.5. TraceInterceptor.java

~~~java
package com.example.mvcdemo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

public class TraceInterceptor implements HandlerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(TraceInterceptor.class);

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        request.setAttribute("intercepted", Boolean.TRUE);

        if (handler instanceof HandlerMethod method) {
            log.info("Interceptor preHandle {}.{}",
                    method.getBeanType().getSimpleName(),
                    method.getMethod().getName());
        }
        return true;
    }

    @Override
    public void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            ModelAndView modelAndView) {
        log.info("Interceptor postHandle status={}",
                response.getStatus());
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {
        log.info("Interceptor afterCompletion error={}",
                ex == null ? "none" : ex.getClass().getSimpleName());
    }
}
~~~

Interceptor nhận handler đã chọn nên có thể log **HandlerMethod**. Với REST response, ví dụ chỉ log trong postHandle; không thêm header quá muộn.

### 9.6. MvcConfig.java

~~~java
package com.example.mvcdemo;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConfig implements WebMvcConfigurer {

    @Bean
    public FilterRegistrationBean<TraceFilter> traceRegistration() {
        FilterRegistrationBean<TraceFilter> registration =
                new FilterRegistrationBean<>(new TraceFilter());
        registration.addUrlPatterns("/api/*");
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        registration.setOrder(10);
        return registration;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new TraceInterceptor())
                .addPathPatterns("/api/**")
                .order(10);
    }
}
~~~

Ở đây Filter dùng **Servlet URL pattern "/api/*"**, interceptor dùng **Spring MVC path pattern "/api/**"**. Hai order 10 **không phải cùng một ordering space**. Demo chỉ xử lý dispatch REQUEST; nếu có async/error dispatch ở production, cần lựa chọn dispatcher types riêng.

### 9.7. HelloController.java

~~~java
package com.example.mvcdemo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public HelloReply hello(HttpServletRequest request) {
        String traceId =
                (String) request.getAttribute("traceId");
        boolean intercepted = Boolean.TRUE.equals(
                request.getAttribute("intercepted"));

        return new HelloReply("xin chào", traceId, intercepted);
    }

    public record HelloReply(
            String message,
            String traceId,
            boolean intercepted) {
    }
}
~~~

### 9.8. application.yml

~~~yaml
server:
  port: 8080
~~~

### 9.9. Chạy và đọc kết quả

~~~bash
mvn spring-boot:run
curl -i http://localhost:8080/api/hello
~~~

Một response **minh họa**:

~~~http
HTTP/1.1 200 OK
X-Trace-Id: 123e4567-e89b-12d3-a456-426614174000
Content-Type: application/json

{"message":"xin chào","traceId":"123e4567-e89b-12d3-a456-426614174000","intercepted":true}
~~~

Giá trị UUID **được tạo ngẫu nhiên**, không phải stdout cố định. Header X-Trace-Id và field traceId trong JSON phải bằng nhau. Log có thể hiển thị Filter before, Interceptor preHandle, postHandle, afterCompletion, Filter after, nhưng log giữa nhiều request đồng thời có thể xen kẽ.

### 9.10. MvcChainTest.java

~~~java
package com.example.mvcdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class MvcChainTest {

    @Autowired
    MockMvc mvc;

    @Test
    void servletFilterAndMvcInterceptorBothRun() throws Exception {
        MvcResult result = mvc.perform(get("/api/hello"))
                .andExpect(status().isOk())
                .andExpect(header().exists("X-Trace-Id"))
                .andExpect(jsonPath("$.message").value("xin chào"))
                .andExpect(jsonPath("$.intercepted").value(true))
                .andReturn();

        String traceId =
                result.getResponse().getHeader("X-Trace-Id");
        assertThat(traceId).isNotBlank();
        assertThat(result.getResponse().getContentAsString())
                .contains(traceId);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

MockMvc kiểm tra filter và MVC handler pipeline trong test context nhưng **không mở kết nối Tomcat thật**. Khi cần xác minh error/async dispatch, socket timeout hoặc thứ tự Filter của Servlet container với proxy, cần bổ sung HTTP integration test.

## 10. Ví dụ Spring WebFlux riêng biệt: WebFilter

Không đặt mã MVC và WebFlux vào cùng dự án mẫu. Dự án thứ hai dùng **spring-boot-starter-webflux**, Reactor Netty và cổng 8081. Một WebFilter tạo traceId trong ServerWebExchange, thêm response header và log khi reactive pipeline hoàn thành.

### 10.1. Cấu trúc

~~~text
webflux-chain-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/reactivedemo/
    │   │   ├── ReactiveDemoApplication.java
    │   │   ├── TraceWebFilter.java
    │   │   └── ReactiveController.java
    │   └── resources/application.yml
    └── test/java/com/example/reactivedemo/
        └── ReactiveChainTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-chain-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

Nếu thêm đồng thời **spring-boot-starter-web** và **spring-boot-starter-webflux**, Spring Boot mặc định thường chọn **Spring MVC**, làm WebFlux demo không còn chạy đúng kiến trúc dự kiến.

### 10.3. ReactiveDemoApplication.java

~~~java
package com.example.reactivedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveDemoApplication.class, args);
    }
}
~~~

### 10.4. TraceWebFilter.java

~~~java
package com.example.reactivedemo;

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
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
public class TraceWebFilter implements WebFilter {

    private static final Logger log =
            LoggerFactory.getLogger(TraceWebFilter.class);

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {

        String traceId = UUID.randomUUID().toString();
        exchange.getAttributes().put("traceId", traceId);
        exchange.getResponse().getHeaders()
                .set("X-Trace-Id", traceId);

        long start = System.nanoTime();

        return chain.filter(exchange)
                .doOnError(error -> log.warn(
                        "WebFilter error type={}",
                        error.getClass().getSimpleName()))
                .doFinally(signal -> {
                    long elapsedMs =
                            (System.nanoTime() - start) / 1_000_000;
                    log.info(
                            "WebFilter finished traceId={} signal={} elapsedMs={}",
                            traceId, signal, elapsedMs);
                });
    }
}
~~~

**@Component** đăng ký WebFilter với Spring WebFlux; **@Order** điều khiển thứ tự bean. Con số order chỉ để minh họa khi không có Spring Security; trong ứng dụng thật phải kiểm tra toàn bộ reactive security/proxy chain.

TraceId được lưu trong **exchange attributes**, không nằm trong instance variable của singleton WebFilter. Header được đặt **trước khi response commit**. **doFinally** có thể nhận completion, error hoặc cancel; không được khẳng định mọi lỗi đã được WebExceptionHandler xử lý đều tới doOnError.

### 10.5. ReactiveController.java

~~~java
package com.example.reactivedemo;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveController {

    @GetMapping("/api/hello")
    public Mono<HelloReply> hello(ServerWebExchange exchange) {
        String traceId = exchange.getAttribute("traceId");
        return Mono.just(
                new HelloReply("xin chào", traceId, "WebFilter"));
    }

    @GetMapping(
            path = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.just("one", "two")
                .delayElements(Duration.ofMillis(100))
                .map(value -> ServerSentEvent.<String>builder()
                        .event("tick")
                        .data(value)
                        .build());
    }

    public record HelloReply(
            String message,
            String traceId,
            String source) {
    }
}
~~~

Request /api/hello cho thấy cả header và JSON cùng dùng một traceId của ServerWebExchange. Endpoint /api/events phát **hai SSE events** rồi hoàn tất, giúp quan sát **doFinally** sau completion.

### 10.6. application.yml

~~~yaml
server:
  port: 8081
~~~

### 10.7. Chạy và thử

~~~bash
mvn spring-boot:run
curl -i http://localhost:8081/api/hello
~~~

Response ví dụ:

~~~http
HTTP/1.1 200 OK
X-Trace-Id: 123e4567-e89b-12d3-a456-426614174000
Content-Type: application/json

{"message":"xin chào","traceId":"123e4567-e89b-12d3-a456-426614174000","source":"WebFilter"}
~~~

UUID thay đổi theo request. Để nhận stream hữu hạn:

~~~bash
curl -i -N -H "Accept: text/event-stream" \
  http://localhost:8081/api/events
~~~

Các frame có dạng:

~~~text
event:tick
data:one

event:tick
data:two

~~~

### 10.8. ReactiveChainTest.java

~~~java
package com.example.reactivedemo;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveChainTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void filterSetsHeaderAndExchangeAttribute() {
        client.get().uri("/api/hello")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().exists("X-Trace-Id")
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message").isEqualTo("xin chào")
                .jsonPath("$.source").isEqualTo("WebFilter")
                .jsonPath("$.traceId").isNotEmpty();
    }

    @Test
    void finiteSseStreamReturnsEventFrames() {
        client.get().uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .expectBody()
                .consumeWith(result ->
                        assertThat(result.getResponseBody())
                                .isNotNull());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Bộ test kiểm tra JSON, X-Trace-Id và SSE media type trên HTTP thật với random port. Test stream hữu hạn chưa đo **độ trễ flush từng event** hay cancellation; cần subscriber nhận từng event và hủy stream để kiểm tra những khía cạnh đó.

## 11. Những lỗi điển hình và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Interceptor không thấy 401/403 | Security filter chặn trước MVC | Kiểm tra SecurityFilterChain |
| Filter chạy hai lần | Vừa auto-register vừa add filter vào Spring Security | Chỉ dùng một registration, setEnabled(false) khi cần |
| postHandle không thêm được header JSON | ResponseBody đã commit | Đặt sớm trong Filter/Controller/ResponseEntity |
| afterCompletion không chạy ở interceptor trả false | Chính interceptor đó chặn handler | Cleanup ngay khi preHandle false |
| Log duration quá nhỏ với async MVC | Filter chain kết thúc dispatch đầu | Theo dõi ASYNC/ERROR dispatch và async callbacks |
| WebFilter block event loop | block(), Thread.sleep, JDBC blocking | Dùng non-blocking API/offload có kiểm soát |
| TraceId reactive sai giữa requests | Mutable singleton field/ThreadLocal | ServerWebExchange attributes hoặc Reactor Context |
| Body @RequestBody rỗng | Filter đã consume ServletInputStream | Không đọc body sớm hoặc wrapper đúng |
| WebFlux body bị consumed | WebFilter tự subscribe Flux<DataBuffer> | Tránh consume/replay thiếu kiểm soát |
| WebFilter không thấy lỗi server trả 500 | Downstream handler đã map exception thành response | Log status, quan sát metrics và exception handler |
| Servlet Filter không chạy ở WebFlux Netty | Không có Servlet filter chain | Dùng WebFilter |
| @ControllerAdvice không thấy lỗi Filter | Lỗi xảy ra trước DispatcherServlet | Filter/container error handling |
| Response header mất trong doFinally | Header đã commit | Đặt trước chain hoặc beforeCommit |
| WebFilter order làm lệch security/cors | Chọn order không phù hợp | Dùng cấu hình security/cors chính thức |
| Interceptor không chạy với URL lạ | Không có HandlerExecutionChain hoặc pattern không phù hợp | Kiểm tra HandlerMapping/static resources |

### 11.1. Quy trình điều tra

1. Xác định **application web type** và server đang thực sự chạy.
2. Xem tất cả Servlet Filter registrations, DispatcherType, @Order, SecurityFilterChain và URL patterns.
3. Xem MVC InterceptorRegistry, include/exclude patterns, handler mapping và async callbacks.
4. Với WebFlux, xem các bean WebFilter, thứ tự @Order, SecurityWebFilterChain và reactor operators.
5. Gửi request thành công, request bị security chặn, request không khớp và request có exception.
6. Kiểm tra status, response headers, trace ID, log ordering và liệu body đã commit.
7. Khi dùng async/streaming, thử client disconnect để kiểm tra cleanup và cancellation.
8. Không bật logging raw body nhạy cảm hoặc TRACE dài hạn trong production.

## 12. Checklist production

- [ ] Chọn cơ chế phù hợp stack: Servlet Filter / MVC Interceptor / WebFlux WebFilter.
- [ ] Đăng ký Filter một lần và có order rõ ràng.
- [ ] Kiểm soát URL patterns và DispatcherType.REQUEST/ASYNC/ERROR theo yêu cầu.
- [ ] Không dùng interceptor làm lớp authorization chính.
- [ ] Không dùng postHandle để thay JSON body đã được viết.
- [ ] Dọn tài nguyên đúng khi preHandle false, exception, async và cancel.
- [ ] Không dùng block() trong WebFilter/Netty event loop.
- [ ] Không đưa per-request state vào singleton fields hoặc ThreadLocal không quản lý.
- [ ] Không đọc request body hai lần hoặc cache vô hạn.
- [ ] Bảo vệ dữ liệu nhạy cảm khi log, tracing và chuẩn hóa exception.
- [ ] Kiểm thử normal/error/short-circuit/async/reactive streaming.
- [ ] Dùng Spring Security, Micrometer Observation khi yêu cầu tương ứng.
- [ ] Chọn phiên bản Spring Boot còn được hỗ trợ bảo mật cho production.

## 13. Tài liệu tham khảo chính thức

1. Spring Framework 6.2 – Servlet Filters/OncePerRequestFilter: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
2. Spring Framework 6.2 – MVC HandlerInterceptor: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html
3. Spring Framework 6.2 – Configuring MVC Interceptors: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html
4. Spring Framework 6.2 – MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
5. Spring Framework 6.2 – WebFlux Reactive Core và WebFilter: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
6. Spring Framework – WebFilter API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/server/WebFilter.html
7. Spring Boot 3.5 – Embedded Web Servers, registering Filters: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
8. Spring Boot 3.5 API – FilterRegistrationBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html
9. Spring Security – Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
10. Spring Security – Reactive WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html

## 14. Tổng kết

**Servlet Filter** hoạt động ở tầng Servlet, bao quanh request trước DispatcherServlet. **HandlerInterceptor** hoạt động trong chuỗi xử lý của Spring MVC sau khi HandlerMapping xác định handler, phù hợp cho logic gắn với controller và ModelAndView nhưng không phải lớp security chính. **WebFilter** hoạt động ở tầng reactive của Spring WebFlux, xử lý ServerWebExchange và Mono<Void> có thể quan sát complete, error và cancel.

Chọn đúng component theo **stack, thời điểm, phạm vi, vòng đời request và nhu cầu bảo mật**. Test không chỉ trường hợp thành công mà cả request bị chặn, error/async dispatch và response đã commit.
# Phân biệt Servlet Filter, HandlerInterceptor, AOP và ControllerAdvice trong Spring MVC

> **Phạm vi:** Spring Web MVC trên Servlet stack, Java 17+ và Spring Boot 3.x / Spring Framework 6.x. Bốn cơ chế này đều có vẻ “chạy trước hoặc sau” một công việc, nhưng chúng can thiệp ở **các tầng và thời điểm khác nhau**: `Servlet Filter` bao quanh request/response trong chuỗi Servlet; `HandlerInterceptor` quan sát chuỗi thực thi handler đã được Spring MVC ánh xạ; **Spring AOP** can thiệp vào lời gọi **phương thức của Spring bean thông qua proxy**; `@ControllerAdvice` cung cấp các chức năng dùng chung cho **MVC controller**, đặc biệt xử lý lỗi và tùy biến binding/model. Không nên coi bốn loại là tương đương hoặc thay thế được cho nhau.

## 1. Bức tranh tổng thể: mỗi cơ chế đứng ở đâu?

Một request đi vào Spring Boot Servlet app theo mô hình đơn giản sau:

```text
HTTP client
    |
Servlet container (Tomcat / Jetty / ...)
    |
    v
[ Servlet Filter 1 ] --+
    |                  | before/after FilterChain.doFilter(...)
[ Servlet Filter 2 ] --+
    |
    v
DispatcherServlet
    |
    v
HandlerMapping chọn handler / HandlerExecutionChain
    |
    v
[ HandlerInterceptor.preHandle ]
    |
    v
HandlerAdapter gọi @Controller method
    |                 \
    |                  \-> @ControllerAdvice @InitBinder / @ModelAttribute
    |                                   (khi giải quyết model/binding)
    v
Controller gọi service Spring bean (proxy nếu có)
    |
    v
[ Spring AOP @Around / @Before / @After ... ]
    |
    v
service / repository / nghiệp vụ
    |
    +------ nếu exception trong MVC -------------------+
    |                                                |
    v                                                v
HTTP body / view                              MVC exception resolver
    |                                           |
    |                                  @ExceptionHandler local,
    |                                  rồi @ControllerAdvice phù hợp
    |
[ HandlerInterceptor.postHandle ] (luồng đồng bộ thành công)
    |
View rendering nếu có
    |
[ HandlerInterceptor.afterCompletion ]
    |
Quay lại filter chain (finally / logic sau doFilter)
    |
HTTP response
```

Sơ đồ cố ý lược bỏ nhiều chi tiết: validation có thể xảy ra **trước khi controller method bắt đầu**; Spring Security thường là filter chain riêng; nội dung JSON của `@ResponseBody` thường đã được ghi trong `HandlerAdapter` **trước khi** `postHandle` được gọi; async request có thêm dispatch; exception xử lý thành công có thể khiến `afterCompletion` nhận `ex = null`. Những chi tiết đó làm nên khác biệt thực tế.

### 1.1. Bảng so sánh nhanh

| Khía cạnh | Servlet Filter | HandlerInterceptor | Spring AOP | ControllerAdvice |
| --- | --- | --- | --- | --- |
| Thuộc lớp nào? | Servlet API | Spring Web MVC | Spring Core AOP/proxy | Spring Web MVC controller infrastructure |
| Điểm móc | Servlet request/response dispatch | `HandlerExecutionChain` sau khi Spring MVC chọn handler | Lời gọi method được Spring proxy intercept | Resolver cho exception, binder/model và advice đặc biệt |
| Phạm vi điển hình | HTTP path và dispatcher types đã đăng ký, bao gồm cả request không vào MVC | HandlerMapping / path patterns được đăng ký | Method của Spring-managed beans khớp pointcut | Controller được scope advice áp dụng |
| Vào trước handler? | Có, từ trước `DispatcherServlet` | `preHandle` có | Có nếu AOP pointcut bao method đang gọi | Không phải “preHandle” chung; một số hooks áp dụng khi chuẩn bị model/binder |
| Hậu xử lý | Code sau `chain.doFilter` / `finally` | `postHandle`, `afterCompletion` | `@After`, `@AfterReturning`, `@AfterThrowing`, `@Around` | `@ExceptionHandler`, `ResponseBodyAdvice` và những chức năng chuyên biệt |
| HTTP request trực tiếp? | Có, `ServletRequest`/`HttpServletRequest` | Có, `HttpServletRequest` và handler | Không mặc định cần HTTP; có thể chạy trong batch/scheduler | Có ngữ cảnh MVC tùy method/hook |
| Có thể chặn request? | Có, không gọi `chain.doFilter` | Có, `preHandle` trả `false` | Có thể thay/không gọi `proceed()` nhưng chỉ cho method có proxy | Có thể biến một exception thành HTTP response; không phải filter |
| Phù hợp nhất | HTTP policy sớm, logging/correlation, encoding, security filter | Đo/đính metadata liên quan handler MVC, locale và xử lý quanh routing | Transactions, metrics/service logging, policy xuyên layer | REST error contract, shared `@InitBinder`, shared `@ModelAttribute`, response body advice |
| Giới hạn quan trọng | Không tự biết controller method đã chọn | Không nên dùng làm lớp bảo mật chính | Self-invocation không đi qua proxy | Không tự bắt mọi lỗi từ Servlet Filter |
| Đăng ký thường gặp | `@Component`/`FilterRegistrationBean` | `WebMvcConfigurer#addInterceptors` | `@Aspect` + AOP auto-proxy config/starter | `@ControllerAdvice` / `@RestControllerAdvice` bean |

**Nguyên tắc chọn đúng:** nếu chính sách liên quan **request vào ứng dụng**, nghĩ Filter; nếu cần **handler MVC đã được map**, nghĩ Interceptor; nếu liên quan **method nghiệp vụ**, nghĩ AOP; nếu muốn **thống nhất lỗi/binding/model controller**, nghĩ ControllerAdvice.

## 2. Servlet Filter: can thiệp ở ranh giới HTTP/Servlet

`jakarta.servlet.Filter` thuộc Servlet API, không phải annotation riêng của Spring MVC. Spring Boot 3.x dùng namespace **`jakarta.servlet.*`**; mã Spring Boot 2.x cũ thường dùng **`javax.servlet.*`**, không thể trộn import tùy ý.

Cấu trúc interface:

```java
public interface Filter {
    void init(FilterConfig filterConfig) throws ServletException;
    void doFilter(ServletRequest request,
                  ServletResponse response,
                  FilterChain chain)
            throws IOException, ServletException;
    void destroy();
}
```

Đây là chữ ký mô tả Servlet API (các method init/destroy có thể có default implementation tùy API version). Điểm quan trọng là `chain.doFilter(request,response)`: filter giao quyền cho phần tiếp theo. Nếu filter **không** gọi `chain.doFilter`, request có thể dừng tại filter đó (nếu tự trả response thích hợp).

### 2.1. Filter bao quanh request như thế nào?

```java
@Override
public void doFilter(ServletRequest request,
                     ServletResponse response,
                     FilterChain chain)
        throws IOException, ServletException {

    long started = System.nanoTime();
    try {
        chain.doFilter(request, response);
    } finally {
        long duration = System.nanoTime() - started;
        System.out.println("request nanos=" + duration);
    }
}
```

Đây là **method minh họa**, cần đặt trong một lớp triển khai `Filter` và import Servlet classes. Code trước `doFilter` chạy trước chuỗi tiếp theo; code trong `finally` chạy khi chuỗi trả điều khiển hoặc ném exception. Nếu response đã committed, sửa status/header ở `finally` có thể quá muộn.

**Những request Filter có thể thấy:** route MVC, static resources, servlet endpoint khác và một số error/async dispatch tùy filter registration. Không khẳng định mọi Filter chắc chắn chạy cho **mọi dispatcher type**; việc đăng ký URL patterns và các `DispatcherType.REQUEST`, `ASYNC`, `ERROR`, `FORWARD`, `INCLUDE` quyết định phạm vi.

### 2.2. Dùng `OncePerRequestFilter` của Spring

Trong app Spring MVC, thường dùng:

```java
@Component
class CorrelationFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        request.setAttribute("traceId", "demo-trace");
        response.setHeader("X-Trace-Id", "demo-trace");
        chain.doFilter(request, response);
    }
}
```

Đây là snippet class; cần import `org.springframework.web.filter.OncePerRequestFilter`, `org.springframework.stereotype.Component` và Jakarta HTTP/Servlet API. `OncePerRequestFilter` giúp tránh chạy lặp ngoài ý muốn trong một **dispatch** theo cơ chế đánh dấu request; đừng diễn giải thành “chính xác một lần duy nhất trong toàn bộ mọi thread và async/error dispatch”. Với async/error dispatch, xem các hook `shouldNotFilterAsyncDispatch()` và `shouldNotFilterErrorDispatch()` và dispatcher registration.

### 2.3. Đăng ký filter và thứ tự

Spring Boot có thể đăng ký bean `Filter` (ví dụ `@Component`) với servlet container. Khi cần giới hạn đường dẫn/độ ưu tiên rõ ràng, dùng `FilterRegistrationBean`:

```java
@Bean
FilterRegistrationBean<MyFilter> myFilterRegistration(MyFilter filter) {
    FilterRegistrationBean<MyFilter> bean = new FilterRegistrationBean<>();
    bean.setFilter(filter);
    bean.addUrlPatterns("/api/*");
    bean.setOrder(10);
    return bean;
}
```

Đây là snippet cấu hình, cần lớp `MyFilter` và import `FilterRegistrationBean`, `@Bean`; **không** đặt đồng thời nhiều registration độc lập cho cùng filter nếu không muốn lặp. `setOrder` biểu diễn thứ tự đăng ký tương đối giữa filter của Boot trong những điều kiện áp dụng. Thứ tự tuyệt đối còn phụ thuộc Security filter chain, Servlet registration và dispatcher types: dùng integration test thay vì đoán chỉ từ con số.

### 2.4. Khi nào chọn Filter?

Phù hợp với:
- Tạo trace/correlation ID trước cả MVC; ghi log request, latency tổng.
- Chuẩn hóa encoding/request wrappers và response headers cần đặt sớm.
- Chính sách áp dụng cho cả static resources hoặc non-MVC servlets trong servlet application.
- Rate limiting và bảo vệ ranh giới HTTP khi được thiết kế tại lớp filter/gateway thích hợp.
- Spring Security sử dụng `FilterChainProxy` trong Servlet filter chain, vì authentication/authorization cần diễn ra đủ sớm.

**Không phù hợp:** truy cập trực tiếp `HandlerMethod` đã chọn để biết annotation controller, trừ khi tự tích hợp sâu hoặc để Interceptor làm việc ấy. Filter chạy **trước** khi DispatcherServlet chọn MVC handler, nên không mặc định biết controller method nào sẽ được gọi.

## 3. HandlerInterceptor: can thiệp vào chuỗi thực thi MVC

`org.springframework.web.servlet.HandlerInterceptor` chạy trong Spring MVC khi `HandlerMapping` xác định handler và tạo `HandlerExecutionChain`. API chủ yếu:

```java
public interface HandlerInterceptor {
    boolean preHandle(HttpServletRequest request,
                      HttpServletResponse response,
                      Object handler) throws Exception;

    void postHandle(HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler,
                    ModelAndView modelAndView) throws Exception;

    void afterCompletion(HttpServletRequest request,
                         HttpServletResponse response,
                         Object handler,
                         Exception ex) throws Exception;
}
```

Đây là chữ ký tóm tắt (interface có default method ở Spring MVC hiện đại). Ý nghĩa:

- `preHandle`: gọi **trước khi handler được invoke**. Trả `true` để tiếp tục; trả `false` để dừng phần còn lại của chain và bỏ qua handler. Nếu dừng, interceptor tự chịu trách nhiệm cung cấp response thích hợp.
- `postHandle`: gọi sau khi handler xử lý **thành công trong luồng đồng bộ**, trước khi render view truyền thống. Với `@ResponseBody` / `ResponseEntity`, body có thể đã được converter ghi vào response tại thời điểm này.
- `afterCompletion`: gọi khi xử lý request hoàn tất cho những interceptor đã chạy `preHandle` thành công, kể cả nhiều trường hợp exception. Hữu ích để dọn thread-local/metrics; tham số `ex` **không nhất thiết** phản ánh mọi exception đã được resolver xử lý.

### 3.1. Đăng ký interceptor trong Spring Boot MVC

```java
@Configuration
class WebConfiguration implements WebMvcConfigurer {

    private final TraceInterceptor traceInterceptor;

    WebConfiguration(TraceInterceptor traceInterceptor) {
        this.traceInterceptor = traceInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(traceInterceptor)
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/public/**");
    }
}
```

Đây là snippet cần `TraceInterceptor` là Spring bean và import `Configuration`, `WebMvcConfigurer`, `InterceptorRegistry`. Path patterns ở đây áp cho MVC handler mappings thuộc cấu hình MVC; không biến nó thành Filter cho toàn container. Controller nào match theo MVC handler mapping tương ứng thì interceptor được áp dụng.

Có thể khai báo `MappedInterceptor` bean khi cần nhiều `HandlerMapping` sử dụng chung. Nếu có các handler mappings tùy biến hoặc framework phụ, cần xác minh phạm vi đăng ký Java config. Một `HandlerInterceptor` có thể chạy cả với resource handler nếu pattern match; nó **không nhất thiết chỉ chạy cho method gắn `@RequestMapping`**.

### 3.2. HandlerMethod và thông tin controller

```java
@Override
public boolean preHandle(HttpServletRequest request,
                         HttpServletResponse response,
                         Object handler) {

    if (handler instanceof HandlerMethod hm) {
        String methodName = hm.getMethod().getName();
        request.setAttribute("controllerMethod", methodName);
    }
    return true;
}
```

Snippet trên chỉ là method. `HandlerMethod` cho phép biết method/controller đã được Spring MVC chọn. Nhưng `handler` được khai báo `Object` vì có những handler không phải `HandlerMethod` (chẳng hạn resource handler). Luôn kiểm tra `instanceof`.

### 3.3. Nhiều interceptor: thứ tự callback

Nếu interceptor A đăng ký trước B, một request đồng bộ không lỗi và cả hai `preHandle` trả `true` thường có trình tự:

```text
A.preHandle
B.preHandle
@Controller handler
B.postHandle
A.postHandle
View render (nếu có)
B.afterCompletion
A.afterCompletion
```

Điều này giống cấu trúc “bao quanh”: pre theo thứ tự đăng ký; post/after theo thứ tự ngược. Nếu B trả `false`, handler không chạy, callback `afterCompletion` chỉ áp cho những interceptor trước đó đã hoàn tất `preHandle=true`; không được mặc định `afterCompletion` của B sẽ chạy khi chính B từ chối.

### 3.4. Tại sao không thêm header trong `postHandle` của REST JSON?

Với `@ResponseBody`, `HandlerAdapter` có thể đã ghi/commit response trước khi `postHandle` chạy. Do đó:

```java
// Không đáng tin cậy cho REST response đã ghi:
@Override
public void postHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        ModelAndView modelAndView) {
    response.setHeader("X-Late", "may-not-be-sent");
}
```

Đây là anti-pattern minh họa. Nếu cần header trước khi body được ghi, đặt trong `preHandle`, Filter trước `chain.doFilter` hoặc `ResponseEntity`. Nếu mục tiêu **chỉnh/bao kết cấu body JSON** hoặc thêm logic trước converter write, xem `ResponseBodyAdvice` thay vì nghĩ `postHandle` luôn phù hợp.

### 3.5. Lựa chọn bảo mật

Tài liệu chính thức Spring MVC **không khuyến nghị interceptor làm lớp bảo mật chính** vì có thể xảy ra mismatch giữa path matching của interceptor và annotated controller mappings. Hãy dùng **Spring Security** hoặc lớp tương tự hoạt động sớm trong Servlet filter chain. Interceptor hợp lý để bổ sung logging/metrics liên quan handler, localization hoặc kiểm tra điều kiện phụ không được dùng thay authorization chính.

## 4. Spring AOP: cắt ngang lời gọi method của Spring bean

Spring AOP thuộc mô hình **aspect-oriented programming**: áp dụng logic xuyên suốt lên nhiều lời gọi method mà không sao chép cùng đoạn code vào từng service.

Các thuật ngữ:

| Khái niệm | Ví dụ | Nghĩa |
| --- | --- | --- |
| **Aspect** | Class `@Aspect` | Nơi khai báo logic xuyên suốt |
| **Advice** (AOP) | `@Around` / `@Before` | Code chạy tại join point phù hợp |
| **Join point** | Lời gọi method của proxied bean | Điểm có thể can thiệp |
| **Pointcut** | `execution(* com.example.demo..service..*(..))` | Điều kiện chọn method |
| **Proxy** | JDK dynamic proxy hoặc CGLIB | Object trung gian thực thi advice |
| **ProceedingJoinPoint** | `pjp.proceed()` | Cho phép method gốc tiếp tục từ `@Around` |

**Đừng nhầm thuật ngữ “Advice” trong AOP** với `@ControllerAdvice`: một bên là aspect/proxy method interception, bên kia là controller infrastructure của Web MVC.

### 4.1. Một aspect quanh service method

```java
@Aspect
@Component
class ServiceTimingAspect {

    @Around("execution(* com.example.demo.GreetingService.greet(..))")
    Object time(ProceedingJoinPoint joinPoint) throws Throwable {
        long started = System.nanoTime();
        try {
            return joinPoint.proceed();
        } finally {
            long elapsed = System.nanoTime() - started;
            System.out.println("service nanos=" + elapsed);
        }
    }
}
```

Snippet này cần class `GreetingService` và import AspectJ annotation, Spring component và `ProceedingJoinPoint`. Với Spring Boot 3.x thêm starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

Spring Boot tự cấu hình AOP khi có dependency phù hợp; không luôn cần `@EnableAspectJAutoProxy` thủ công. Aspect chỉ chạy khi call **đi qua proxy** và match pointcut; không phải middleware HTTP. Method chạy từ scheduled task hoặc message consumer cũng có thể được AOP intercept nếu qua proxied bean.

### 4.2. Thế nào là self-invocation?

```java
@Service
class OrderService {

    public void outer() {
        inner(); // lời gọi nội bộ trên 'this', không đi qua proxy
    }

    public void inner() {
        // Pointcut chỉ match inner() thì có thể không chạy ở đây.
    }
}
```

Đây là snippet minh họa. Nếu một method của bean gọi method khác trên **cùng instance** qua `this`, nó không đi qua Spring AOP proxy, nên advice áp lên `inner()` có thể bị bỏ qua. Đây là giới hạn nổi bật của proxy-based Spring AOP. Giải pháp thường phù hợp là tách trách nhiệm sang Spring bean khác rồi inject, thay vì tự gọi qua proxy/hack `AopContext.currentProxy()`.

Tùy proxy mode:
- **JDK dynamic proxy** thường áp dụng theo interface.
- **CGLIB proxy** kế thừa class, bị giới hạn với final class/final method và visibility.
- Spring Boot có defaults riêng có thể chọn class-based proxies; đừng suy luận mặc định chỉ từ quy tắc Java có hay không có interface.

### 4.3. Spring AOP không phải HTTP middleware

AOP thấy **method invocation**, không thấy **tự động mọi URL**. Nó có thể không chạy nếu:
- Bean không thuộc Spring container.
- Method call không đi qua proxy.
- Pointcut không match hoặc method không thể được advised do proxy constraints.
- Đối tượng được tạo trực tiếp bằng `new` thay vì bean được Spring quản lý.

AOP phù hợp cho metrics/service policy, transaction boundaries, auditing lời gọi nghiệp vụ (khi tuân thủ hợp đồng bảo mật) hoặc các behavior xuyên layer. Spring `@Transactional` dựa trên proxy/AOP infrastructure trong cấu hình thường gặp, nên self-invocation cũng là một nguy cơ với transaction method.

**Không dùng AOP để tự triển khai mọi HTTP security check.** Với authentication/authorization trên web, dùng Spring Security filter/method security; đừng chỉ dựa vào một aspect logics tự viết mà bỏ qua đường đi không qua proxy.

## 5. @ControllerAdvice: dùng chung chức năng MVC controller

`@ControllerAdvice` là annotation trên một Spring bean, giúp khai báo những method có vai trò dùng chung cho controller trong phạm vi áp dụng. `@RestControllerAdvice` tương đương `@ControllerAdvice` kèm behavior `@ResponseBody` cho các response method liên quan.

Ba nhóm hook quan trọng nhất:

1. **`@ExceptionHandler`:** chuyển exception khi xử lý MVC thành HTTP response/view lỗi.
2. **`@InitBinder`:** tùy biến `WebDataBinder` cho model binding/formatting/validation.
3. **`@ModelAttribute` methods:** đóng góp các model attributes dùng chung cho controller.

Ngoài ra, một `@ControllerAdvice` bean có thể triển khai `ResponseBodyAdvice<T>` để can thiệp lúc response body chuẩn bị được ghi bởi converter. Đây là extension interface riêng, **không đồng nghĩa mọi class `@ControllerAdvice` tự có một pre/post callback quanh mọi request**.

### 5.1. Exception handler dùng chung

```java
@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> badArgument(
            IllegalArgumentException ex) {

        return ResponseEntity.badRequest()
                .body(Map.of("error", "Invalid request"));
    }
}
```

Đây là snippet class; import `RestControllerAdvice`, `ExceptionHandler`, `ResponseEntity` và `java.util.Map`. Nếu controller/service (trong vòng đời request mà MVC resolver thấy) ném `IllegalArgumentException`, Spring chọn handler này khi không có local handler ưu tiên tương ứng.

**Quy tắc ưu tiên:** local `@ExceptionHandler` trong controller được xem trước global handlers từ `@ControllerAdvice`. Khi nhiều advice beans cùng khớp, thứ tự `@Order` và exception matching root/cause cũng quan trọng. Không nên đặt một generic `@ExceptionHandler(Exception.class)` rồi trả HTTP 400 cho mọi lỗi hệ thống.

### 5.2. InitBinder để kiểm soát form binding

```java
@ControllerAdvice(annotations = Controller.class)
class FormBinderAdvice {

    @InitBinder("profileForm")
    void onlyPublicFields(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "bio");
    }
}
```

Snippet minh họa: `@InitBinder` áp dụng cho model attribute `profileForm` ở các controller thuộc phạm vi advice. Nó không tự tạo một HTTP filter; cũng không áp dụng như JSON allowlist cho Jackson `@RequestBody`. Hãy bảo vệ data binding bằng DTO riêng và kiểm tra quyền cập nhật ở service.

### 5.3. Shared model attributes

```java
@ControllerAdvice
class PageModelAdvice {

    @ModelAttribute("siteName")
    String siteName() {
        return "Demo MVC";
    }
}
```

Method này giúp các controller tạo view có attribute `siteName` nếu thuộc phạm vi advice. Không dùng nó để load các dữ liệu đắt tiền cho mọi request mà không cần; nếu chỉ REST APIs thì việc bổ sung model có thể không hữu ích.

### 5.4. ResponseBodyAdvice cho JSON

Nếu muốn chỉnh **response body** trước converter write:

```java
@RestControllerAdvice
class VersionAdvice implements ResponseBodyAdvice<Object> {

    @Override
    public boolean supports(MethodParameter returnType,
            Class<? extends HttpMessageConverter<?>> converterType) {
        return true; // Demo: áp dụng rộng; production phải chọn lọc.
    }

    @Override
    public Object beforeBodyWrite(Object body,
            MethodParameter returnType,
            MediaType selectedContentType,
            Class<? extends HttpMessageConverter<?>> converterType,
            ServerHttpRequest request,
            ServerHttpResponse response) {
        response.getHeaders().add("X-API-Version", "1");
        return body;
    }
}
```

Đây là **snippet riêng, không thêm vào code ví dụ chạy ở mục 8**. Cần import `ResponseBodyAdvice`, `MethodParameter`, `HttpMessageConverter`, `MediaType`, `ServerHttpRequest`, `ServerHttpResponse` và `RestControllerAdvice`. Chức năng chạy gần thời điểm message converter ghi response, khác với `HandlerInterceptor.postHandle`. Với `supports()=true`, cần đặc biệt kiểm tra text, binary, streaming và lỗi để tránh can thiệp vào response không thích hợp. Nếu chỉ thêm header tĩnh, Filter hoặc `ResponseEntity` có thể đơn giản hơn.

### 5.5. Điều ControllerAdvice không làm

- Không bao trùm mọi Servlet request như Filter.
- Không tự được gọi một lần trước và sau **mọi controller handler**; callback phụ thuộc chức năng (error/binder/model/body).
- Không tự bắt exception xuất phát hoàn toàn từ một Servlet filter **trước khi** `DispatcherServlet` được gọi, vì lỗi có thể chưa đi vào MVC exception resolver.
- Không phải một AOP aspect: `@ControllerAdvice` **không** xử lý arbitrary method calls trong service/batch.
- Không mặc định vượt qua local `@ExceptionHandler` khi cả hai cùng match.

### 5.6. Giới hạn phạm vi của global advice

```java
@RestControllerAdvice(basePackages = "com.example.demo.api")
class ApiOnlyErrors {
    // ...
}
```

Annotation cũng hỗ trợ `basePackageClasses`, `assignableTypes` hoặc `annotations` để áp dụng cho nhóm controller. Không phải cứ tên “global” là không thể giới hạn. Dùng selector có mục đích, tránh xử lý các lỗi HTML view và lỗi REST bằng một body contract không phù hợp.

## 6. So sánh thứ tự callback trong những tình huống thật

### 6.1. Request JSON thành công đồng bộ

Ví dụ client gọi `GET /api/greet?name=Lan`:

```text
TraceFilter trước chain.doFilter
  -> TraceInterceptor.preHandle
     -> Controller method bắt đầu
        -> ServiceTimingAspect.before/proceed
           -> GreetingService.greet
        <- ServiceTimingAspect.after
     <- Controller trả DTO
     -> HttpMessageConverter ghi JSON
  <- TraceInterceptor.postHandle (JSON có thể đã ghi)
  <- TraceInterceptor.afterCompletion
TraceFilter finally / sau chain.doFilter
```

Không phải mọi callback đều có cấu trúc before/after giống nhau, và async handling có thể làm chuỗi khác đi. Một `@RestControllerAdvice` chỉ khai báo `@ExceptionHandler` sẽ **không chạy** trong success path trên.

### 6.2. Service ném exception, được ControllerAdvice xử lý

```text
Filter before
  -> Interceptor.preHandle
     -> Controller
        -> AOP around service
           -> service throws IllegalArgumentException
        <- AOP finally
     -> MVC catches exception
     -> @RestControllerAdvice @ExceptionHandler
     -> HTTP 400 + JSON error
  -> Interceptor.afterCompletion
Filter finally
```

`postHandle` thông thường **không chạy** trên đường handler ném exception; exception resolver có thể tạo response riêng. `afterCompletion` có thể được gọi sau khi MVC xử lý xong, nhưng tham số `ex` có thể `null` nếu exception đã được resolver xử lý. Đừng dùng `afterCompletion(ex != null)` làm nguồn duy nhất để đếm mọi exception HTTP.

### 6.3. Filter chặn request trước MVC

```text
Filter detects invalid early request
  -> response.setStatus(400)
  -> write safe body
  -> return without chain.doFilter
     X DispatcherServlet
     X HandlerInterceptor
     X @Controller
     X @ControllerAdvice @ExceptionHandler
```

Vì request không vào MVC, local/global MVC exception handlers không có cơ hội xử lý như bình thường. Nếu muốn error contract thống nhất từ Filter/Spring Security, sử dụng handler/writer phù hợp với filter stack hoặc chủ động chuyển giao qua một interface được thiết kế; đừng giả định `@RestControllerAdvice` tự bắt lỗi trước MVC.

### 6.4. Request đến URL không có MVC handler

Một Filter đã đăng ký thích hợp **có thể** chạy và thấy request. Interceptor chỉ chạy nếu MVC tìm được một handler mapping phù hợp (lưu ý framework có thể có `ResourceHttpRequestHandler` cho static resources). Spring Boot error page hoặc fallback handler có thể xử lý request theo cấu hình; đừng nghĩ mọi 404 đều làm `HandlerInterceptor.preHandle` chạy cho một controller method.

## 7. Ví dụ đầy đủ chạy được: quan sát cả bốn cơ chế

Đây là ứng dụng **Spring Boot 3.x, Java 17+**, dùng **Spring Web** và **Spring AOP**. Không thêm Spring Security, database, Thymeleaf hay WebFlux. Đặt mã bên dưới vào duy nhất file `src/main/java/com/example/demo/DemoApplication.java`; một public class, các class khác package-private hợp lệ.

### 7.1. Dependency

Tạo Maven project tại [Spring Initializr](https://start.spring.io/) với Java 17+ và hai dependencies **Spring Web** và **Spring AOP**, tương đương:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
  </dependency>
</dependencies>
```

Đây là fragment trong `pom.xml`; Initializr cung cấp Spring Boot parent/BOM, version, plugins và phần project metadata còn lại. AOP starter cung cấp các thư viện cần cho `@Aspect` và Boot tự cấu hình proxy trong điều kiện bình thường.

### 7.2. Toàn bộ Java source

```java
package com.example.demo;

import java.io.IOException;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

// TẦNG 1: Servlet Filter. Boot đăng ký Filter bean.
@Component
class TraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader("X-Filter", "seen");
        System.out.println("FILTER before");
        try {
            chain.doFilter(request, response);
        } finally {
            System.out.println("FILTER after");
        }
    }
}

// TẦNG 2: MVC HandlerInterceptor.
@Component
class TraceInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        response.setHeader("X-Interceptor", "seen");
        System.out.println("INTERCEPTOR preHandle");
        return true;
    }

    @Override
    public void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            org.springframework.web.servlet.ModelAndView modelAndView) {

        System.out.println("INTERCEPTOR postHandle");
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {

        System.out.println("INTERCEPTOR afterCompletion");
    }
}

@Configuration
class MvcConfig implements WebMvcConfigurer {

    private final TraceInterceptor interceptor;

    MvcConfig(TraceInterceptor interceptor) {
        this.interceptor = interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor)
                .addPathPatterns("/api/**");
    }
}

// TẦNG 3: Spring-managed service qua proxy AOP.
@Service
class GreetingService {

    public String greet(String name) {
        System.out.println("SERVICE greet");

        if ("bad".equalsIgnoreCase(name)) {
            throw new IllegalArgumentException("invalid name");
        }
        return "Hello, " + name;
    }
}

@Aspect
@Component
class ServiceTraceAspect {

    @Around("execution(* com.example.demo.GreetingService.greet(..))")
    public Object around(ProceedingJoinPoint joinPoint)
            throws Throwable {

        System.out.println("AOP before");
        try {
            return joinPoint.proceed();
        } finally {
            System.out.println("AOP after");
        }
    }
}

// Controller chỉ chứa HTTP mapping và gọi service.
@RestController
@RequestMapping("/api")
class GreetingController {

    private final GreetingService service;

    GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet")
    public Map<String, String> greet(
            @RequestParam(defaultValue = "Lan") String name) {

        return Map.of("message", service.greet(name));
    }
}

// TẦNG 4: MVC error policy chung.
@RestControllerAdvice
class ApiErrors {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalidName(
            IllegalArgumentException ex) {

        System.out.println("ADVICE exceptionHandler");
        return ResponseEntity.badRequest()
                .body(Map.of("error", "name invalid"));
    }
}
```

**Những điểm cần đọc đúng:**
- `TraceFilter` dùng `OncePerRequestFilter`, chạy ở Servlet filter chain và đặt `X-Filter` trước khi request vào MVC.
- `TraceInterceptor` đăng ký cho `/api/**`, đặt `X-Interceptor` trong `preHandle` để chắc header có thể được ghi trước body.
- `GreetingService` là Spring `@Service`. Controller inject bean do Spring cung cấp; cuộc gọi tới `greet(...)` đi qua AOP proxy, do đó `ServiceTraceAspect` hoạt động.
- `ServiceTraceAspect` log `AOP before` và `AOP after` kể cả khi `greet(...)` ném exception, vì đoạn sau đặt trong `finally`.
- `ApiErrors` là `@RestControllerAdvice`, chỉ chọn `@ExceptionHandler(IllegalArgumentException.class)` khi exception phù hợp đi tới MVC exception resolver.
- Bài demo dùng `System.out.println` chỉ để quan sát callback; production nên dùng structured logging/tracing/metrics thích hợp. Các request đồng thời có thể khiến dòng log xen kẽ.
- Không có `@EnableAspectJAutoProxy` vì Spring Boot 3.x với starter AOP mặc định đã kích hoạt hạ tầng proxy phù hợp.

### 7.3. Chạy

Từ thư mục Maven project:

```bash
# Linux hoặc macOS
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

Server mặc định chạy tại `http://localhost:8080` nếu chưa đổi `server.port` hoặc context path. Chạy request trong môi trường không có Security/filter ngoài ví dụ để hiểu chuỗi callback.

### 7.4. Request thành công: Filter + Interceptor + AOP, không có error advice

```bash
curl -i 'http://localhost:8080/api/greet?name=Lan'
```

Response chứa:
- HTTP status **200 OK**.
- Header `X-Filter: seen`.
- Header `X-Interceptor: seen`.
- Body JSON (giá trị đúng, thứ tự header không cố định):

```json
{"message":"Hello, Lan"}
```

Với một request đồng bộ duy nhất, log trong console theo chuỗi tiêu biểu:

```text
FILTER before
INTERCEPTOR preHandle
AOP before
SERVICE greet
AOP after
INTERCEPTOR postHandle
INTERCEPTOR afterCompletion
FILTER after
```

Không có `ADVICE exceptionHandler` vì không có exception. Nếu phía ngoài còn filter/container logging, output có thể có thêm dòng không nằm trong snippet.

### 7.5. Request lỗi: ControllerAdvice chuyển exception thành 400

```bash
curl -i 'http://localhost:8080/api/greet?name=bad'
```

Response chứa HTTP status **400 Bad Request**, hai header `X-Filter: seen` và `X-Interceptor: seen`, body:

```json
{"error":"name invalid"}
```

Log chính tiêu biểu:

```text
FILTER before
INTERCEPTOR preHandle
AOP before
SERVICE greet
AOP after
ADVICE exceptionHandler
INTERCEPTOR afterCompletion
FILTER after
```

`INTERCEPTOR postHandle` thường **không xuất hiện** do controller ném exception trước khi hoàn tất handler thành công, sau đó MVC error resolver mới tạo response. `afterCompletion` vẫn là nơi cleanup phù hợp cho interceptor đã thành công ở `preHandle`.

### 7.6. Request ngoài /api/**

```bash
curl -i http://localhost:8080/unknown
```

Filter được đăng ký trên phạm vi URL mặc định của application nên có thể chạy. Interceptor chỉ được map `/api/**`, vì vậy không thể dùng `/unknown` để chứng minh Interceptor đã chạy. Kết quả 404 cụ thể phụ thuộc Spring MVC static resources/error handling hiện hành; `@RestControllerAdvice` ví dụ chỉ xử lý `IllegalArgumentException` và không có nghĩa nó sẽ tạo body cho mọi 404.

## 8. Kiểm thử bằng MockMvc

Để tự động xác minh rằng Filter và Interceptor chèn header, ControllerAdvice chuyển lỗi thành 400, còn service/AOP vẫn được dùng trong quá trình xử lý, thêm dependency test `spring-boot-starter-test` và file `src/test/java/com/example/demo/PipelineTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PipelineTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulRequestTraversesFilterAndInterceptor()
            throws Exception {

        mvc.perform(get("/api/greet")
                        .param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Filter", "seen"))
                .andExpect(header().string("X-Interceptor", "seen"))
                .andExpect(jsonPath("$.message")
                        .value("Hello, Lan"));
    }

    @Test
    void controllerAdviceMapsServiceErrorTo400()
            throws Exception {

        mvc.perform(get("/api/greet")
                        .param("name", "bad"))
                .andExpect(status().isBadRequest())
                .andExpect(header().string("X-Filter", "seen"))
                .andExpect(header().string("X-Interceptor", "seen"))
                .andExpect(jsonPath("$.error")
                        .value("name invalid"));
    }
}
```

Chạy:

```bash
# macOS/Linux
./mvnw test

# Windows
mvnw.cmd test
```

**Giới hạn của test trên:** các assertions này xác minh các headers và responses nhưng **chưa trực tiếp chứng minh AOP advice đã chạy**. Để xác minh AOP độc lập, có thể inject bean service vào test, dùng `AopUtils.isAopProxy(service)` và một mock/spy hoặc metric counter có kiểm soát; đừng kết luận từ response body rằng aspect đã được invoke. Cũng có thể kiểm tra logs trong môi trường thử nghiệm nếu cần, nhưng assertions với metric/test double ít mong manh hơn.

`@SpringBootTest` tạo application context; `@AutoConfigureMockMvc` thiết lập MockMvc và filters khi cấu hình phù hợp. Nếu thêm Spring Security, cần test auth/CSRF theo policy; ví dụ này không bật Security.

## 9. Tình huống nào nên dùng cái nào?

| Mục tiêu | Cơ chế ưu tiên | Vì sao |
| --- | --- | --- |
| Đặt trace ID trước mọi HTTP endpoint | **Servlet Filter** | Có mặt trước DispatcherServlet; dễ dùng request/response wrapper |
| Chuẩn hóa header bảo mật áp toàn ứng dụng | **Security Filter/Servlet Filter** | Chính sách sớm trước khi body/handler chạy |
| Authentication/authorization HTTP | **Spring Security filter chain** (và method security khi cần) | Chính sách bảo mật nhất quán và sớm |
| Biết controller method và annotation nào được match | **HandlerInterceptor** | Có `handler instanceof HandlerMethod` |
| Đo thời gian xử lý MVC handler | **HandlerInterceptor** | Có preHandle/afterCompletion; không đo toàn bộ filter chain |
| Đo thời gian service method kể cả lời gọi ngoài HTTP | **Spring AOP** | Quan sát service bean invocation |
| Transaction trên service method | **Spring transaction abstraction / proxy AOP** | Đây là vấn đề nghiệp vụ, không phải HTTP request |
| Chuyển exception domain thành JSON lỗi thống nhất | **@RestControllerAdvice + @ExceptionHandler** | Đúng tầng HTTP error representation |
| Thêm chung model attribute cho các HTML controllers | **@ControllerAdvice @ModelAttribute** | Tập trung model setup |
| Ràng buộc binding/formatting cho form | **@ControllerAdvice @InitBinder** | Tác động MVC binding |
| Can thiệp vào response body trước message converter | **ResponseBodyAdvice** | Đúng thời điểm serialize |
| Chặn request không phù hợp theo handler-specific metadata | **HandlerInterceptor** cho metadata bổ sung, nhưng **không thay security** | Chạy sau HandlerMapping |
| Xử lý lỗi do Filter xảy ra ngoài MVC | **Filter/security-specific error strategy** | MVC advice không mặc định thấy exception đó |

**Không bắt buộc chọn duy nhất một:** một app production thường đồng thời có Spring Security filters, custom trace filter, MVC interceptors cho correlation metadata, AOP cho service transactions và `@RestControllerAdvice` cho errors. Vấn đề là trách nhiệm phải tách bạch, tránh ghi log/ghi body/validate cùng một thứ ở nhiều lớp.

## 10. Bảo mật: tại sao interceptor không thay Spring Security?

Spring Framework cảnh báo `HandlerInterceptor` có thể không thích hợp làm security layer do sự khác biệt giữa pattern áp cho interceptor và mapping annotation/controller. Ví dụ interceptor match `/admin/**` nhưng những MVC mappings, forwards, dispatcher types và controller method selection có thể phức tạp hơn. Authorization là tính chất cần áp **chính xác và nhất quán** cho mọi đường vào, không thể dựa vào giả định đường dẫn string match đơn giản.

Cách làm đúng:
- Dùng Spring Security `SecurityFilterChain`, `authorizeHttpRequests(...)`, authentication provider, CSRF/session policy khi cần.
- Áp **method security** cho business methods nhạy cảm khi nghiệp vụ yêu cầu (vd. `@PreAuthorize` với cấu hình phù hợp).
- Kiểm tra ownership/tenant ở service bằng identity đã xác thực.
- Chỉ dùng HandlerInterceptor cho bổ trợ không phải hàng rào bảo mật duy nhất.

**Lưu ý:** Servlet Filter tự viết cũng không tự động an toàn như Spring Security. Spring Security cung cấp cả một mô hình authentication, authorization, error handling, exception translation và lifecycle. Nếu chỉ kiểm tra `request.getHeader("X-Role")` do client tự gửi, việc đặt logic trong Filter vẫn **không biến nó thành xác thực tin cậy**.

## 11. Async và ERROR dispatch: các nhánh nâng cao không được bỏ qua

### 11.1. Servlet Filter và dispatcher types

Filter registration có thể được cấu hình cho dispatcher types `REQUEST`, `ASYNC`, `ERROR`, `FORWARD` và `INCLUDE`. Filter không nhất thiết chạy trong mọi dispatcher; behavior phụ thuộc container/Boot registration.

`OncePerRequestFilter` cung cấp các hook:
- `shouldNotFilter(HttpServletRequest)` để bỏ qua request không áp dụng.
- `shouldNotFilterAsyncDispatch()` để chọn tham gia hoặc tránh dispatch async.
- `shouldNotFilterErrorDispatch()` để chọn logic quanh dispatch lỗi.

Nếu dùng ThreadLocal hoặc MDC:
- Đặt context trước `chain.doFilter`.
- Dọn trong `finally` tại dispatch/thread hiện tại.
- Với async, không giả định ThreadLocal tự chuyển sang thread xử lý khác; phải tích hợp propagation rõ ràng.
- Không log token/cookie/password hay toàn request body thô nếu chưa có chính sách bảo vệ dữ liệu.

### 11.2. HandlerInterceptor và async MVC

Nếu handler khởi động async (ví dụ `Callable`, `DeferredResult`), ban đầu Spring MVC có thể **không** gọi `postHandle` / `afterCompletion` ngay khi handler chuyển sang async. Thay vào đó `AsyncHandlerInterceptor.afterConcurrentHandlingStarted(...)` cung cấp callback khi request chuyển sang concurrent handling; sau async dispatch để hoàn tất, interceptor chain có thể chạy lại theo vòng dispatch.

Vì vậy:
- Không tính tổng thời gian async chỉ từ một lần `preHandle`/`postHandle` mà không hiểu lifecycle.
- Cleanup ThreadLocal đúng theo các callback và thread, dùng async-aware tracing khi cần.
- Đừng xác nhận “Filter chạy chính xác một lần toàn request, Interceptor chạy chính xác một lần” với mọi async scenario.

### 11.3. Exception ở filter trước DispatcherServlet

Nếu filter ném exception trước `chain.doFilter`, `@RestControllerAdvice` thường không bắt được vì MVC chưa nắm quyền. Nếu exception phát sinh **bên trong** controller/service và vào MVC exception resolver, advice có thể xử lý. Tránh đặt error body ở Filter sau khi response đã committed; cần chính sách exception handling phù hợp tầng.

### 11.4. Response đã committed

Mọi cơ chế ở các thời điểm khác nhau cần cân nhắc `HttpServletResponse.isCommitted()`. Cụ thể:
- Filter ở đầu chuỗi thường có thể đặt headers trước.
- Interceptor `preHandle` thường còn kịp đặt headers.
- Interceptor `postHandle` có thể quá muộn với `@ResponseBody` JSON.
- AOP ở service không nên tự ghi Servlet response trừ khi thiết kế thực sự yêu cầu; service nên trả kết quả hoặc ném domain exception.
- `ResponseBodyAdvice` chạy trong đường xử lý body của Spring MVC và phù hợp hơn với việc can thiệp converter output.

## 12. Hiệu năng và đo thời gian ở đúng tầng

Một app có ba loại latency khác nhau:

1. **HTTP end-to-end trên server**: đo ở Filter, thường bao gồm các servlet filters/DispatcherServlet nằm **phía sau nó**, cộng thời gian chờ/sync trong phạm vi dispatch. Với async muốn end-to-end đầy đủ cần cơ chế async-aware, không chỉ đo một lượt `doFilter`.
2. **MVC handler processing**: đo Interceptor, gồm handler/controller logic sau preHandle và các bước MVC render/cleanup theo callback.
3. **Service method latency**: đo AOP, chỉ method call match pointcut thông qua proxy.

Nếu `GET /api/orders` mất 250 ms nhưng service chỉ mất 30 ms, chênh lệch có thể nằm ở security, parameter conversion, network I/O, JSON serialization, view rendering hoặc scheduling. Không dùng metric của AOP service để kết luận toàn bộ HTTP response nhanh/chậm.

Với app lớn, cân nhắc Micrometer Observation/tracing tích hợp Spring Boot thay vì tự viết vô số Filter/Aspect thủ công. Tránh tạo nhãn metric chứa ID user, raw URL với giá trị động, exception message hay token vì cardinality và dữ liệu nhạy cảm.

## 13. Lỗi hay gặp và phương án xử lý

| Vấn đề | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Filter không chạy ở endpoint mong muốn | URL pattern hoặc dispatcher type registration sai | Kiểm tra `FilterRegistrationBean`/container mapping |
| Filter chạy hai lần | Trùng đăng ký bean + registration, dispatch khác hoặc nesting | Kiểm tra registrations và `OncePerRequestFilter` logic |
| Interceptor không chạy | Chưa đăng ký qua MVC config, path pattern không khớp hoặc không có HandlerMapping phù hợp | Kiểm tra `addInterceptors`/handler mapping |
| `preHandle=false` nhưng client nhận response rỗng | Chặn chain mà không set status/body | Trả HTTP response thích hợp trước khi return false |
| `postHandle` không chạy khi lỗi | Handler ném exception, đi sang resolver | Cleanup trong `afterCompletion`, xử lý body lỗi ở advice |
| Header đặt trong `postHandle` không thấy | REST converter đã ghi/commit body | Đặt ở Filter/preHandle/ResponseEntity/ResponseBodyAdvice |
| `afterCompletion(ex)` null dù client nhận 4xx | Exception đã được resolver xử lý | Dựa vào status/metric/error handler phù hợp |
| AOP `@Around` không chạy | Chưa có AOP starter, pointcut sai, call không qua proxy | Kiểm tra bean/proxy/pointcut |
| `@Transactional` trên internal method không chạy | Self-invocation `this.inner()` bỏ qua proxy | Tách service hoặc thay thiết kế proxy boundary |
| Advice không bắt lỗi filter | Lỗi xảy ra ngoài MVC | Xử lý tại filter/security layer |
| App startup báo ambiguous exception handlers | Hai `@ExceptionHandler` trùng mapping | Loại/đổi mapping có chủ đích |
| Exception bị đổi thành 200 | Error handler trả body nhưng không đặt status | Dùng `ResponseEntity.status(...)` hoặc `ProblemDetail` |
| Log cùng request thiếu correlation | Trace context không được giữ khi async/thread switch | Dùng tracing/MDC propagation và cleanup đúng |
| Dùng Interceptor để security nhưng route bypass | Handler mapping/path pattern mismatch | Dùng Spring Security FilterChain |
| ControllerAdvice ảnh hưởng endpoint không mong đợi | Không giới hạn scope hoặc generic catch-all | Dùng selectors và error type hẹp |
| Filter che response body của controller | Tự ghi/flush trước hoặc sau `chain.doFilter` không đúng | Kiểm soát response wrappers và commit state |

## 14. Checklist code review

Khi chuẩn bị thêm cross-cutting logic, đặt các câu hỏi:

1. Cần biết HTTP request/response từ **trước MVC** hay chỉ cần handler method đã match?
2. Nếu request không vào MVC (404, static, security reject), logic vẫn phải chạy không?
3. Cần logic chạy khi service được gọi từ scheduled task/message consumer, hay chỉ khi có HTTP?
4. Có tự quản lý exception/status/body hoặc cần chính sách lỗi thống nhất cho REST controllers?
5. Với interceptor, `preHandle`, `postHandle`, `afterCompletion` có hoạt động đúng khi handler lỗi, trả `false` và chạy async?
6. Với AOP, bean/method có đi qua proxy không? Có self-invocation, final/private methods hoặc pointcut quá rộng?
7. Có chạm vào authentication/authorization không? Nếu có, đã dùng Spring Security và kiểm tra quyền ở service chưa?
8. Có ai khác cũng đang thêm header, log trace ID, xử lý cùng exception hoặc thay body không? Có bị **double logging/double write**?
9. Các tests đã kiểm tra cả request thành công, request lỗi, URL không match và, nếu dùng async, callback lifecycle chưa?
10. Các header có được đặt **trước commit**? Các object trong request/ThreadLocal được cleanup đầy đủ chưa?

## 15. Tự kiểm tra và đáp án

**Câu 1.** Muốn đặt correlation ID trước khi request đi vào DispatcherServlet, kể cả khi request bị security filter chặn, cơ chế nào phù hợp?

**Đáp án:** Servlet Filter được đăng ký đúng thứ tự URL/dispatcher. Security-specific policy nên dùng Spring Security infrastructure.

**Câu 2.** Muốn biết `@GetMapping` method được Spring MVC chọn tên gì, dùng gì?

**Đáp án:** HandlerInterceptor, trong `preHandle` kiểm tra `handler instanceof HandlerMethod`.

**Câu 3.** Muốn log mọi lần Spring service method được gọi, kể cả từ scheduler, dùng gì?

**Đáp án:** Spring AOP quanh method phù hợp của managed bean, lưu ý lời gọi phải đi qua proxy và pointcut chính xác.

**Câu 4.** Muốn mọi REST controller trả cấu trúc JSON lỗi thống nhất cho `ProductNotFoundException`, dùng gì?

**Đáp án:** `@RestControllerAdvice` với `@ExceptionHandler(ProductNotFoundException.class)` và status HTTP phù hợp.

**Câu 5.** `HandlerInterceptor.postHandle` có chắc thêm được header khi handler trả `ResponseEntity<Dto>` không?

**Đáp án:** Không. Message converter có thể đã ghi/commit body trước khi `postHandle`. Dùng `preHandle`, `ResponseEntity`, Filter hoặc `ResponseBodyAdvice` theo mục tiêu.

**Câu 6.** Vì sao `@Around` không chạy khi service gọi `this.innerMethod()`?

**Đáp án:** Spring AOP proxy chỉ can thiệp lời gọi đi qua proxy; self-invocation trên `this` đi thẳng vào method của instance.

**Câu 7.** ControllerAdvice bắt được mọi exception từ Servlet Filter trước DispatcherServlet không?

**Đáp án:** Không mặc định. Exception nằm ngoài MVC cần error strategy ở filter/security/servlet layer phù hợp.

**Câu 8.** Dùng HandlerInterceptor để phân quyền thay Spring Security có an toàn không?

**Đáp án:** Không nên. Spring Framework cảnh báo có thể lệch cách khớp path/controller annotations; authentication/authorization nên nằm trong security infrastructure và business authorization ở service.

**Câu 9.** Filter và Interceptor đều có thể đo request time. Kết quả có giống nhau không?

**Đáp án:** Không bắt buộc. Chúng đo phạm vi khác nhau, còn async, serialization, view rendering, filter chain và thread scheduling làm thay đổi số đo.

## 16. Tài liệu chuẩn

- [Spring Framework 6.2 — Handler Interception](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html): `preHandle`, `postHandle`, `afterCompletion`, response committed và khuyến nghị bảo mật.
- [Spring Framework 6.2 — Configure Interceptors](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html): `WebMvcConfigurer#addInterceptors`, mapped patterns và `MappedInterceptor`.
- [Spring Framework 6.2 — Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html): `@ExceptionHandler`, `@InitBinder`, `@ModelAttribute`, phạm vi.
- [Spring Framework 6.2 — Exception Handler](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html): error handling và exception matching.
- [Spring Framework 6.2 — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): `@Aspect`, advice, pointcut và auto-proxy.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation và method constraints.
- [Spring Framework — OncePerRequestFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): dispatch handling và filtering hooks.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): servlet filters, MVC configuration và embedded container integration.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `FilterChainProxy`, `SecurityFilterChain` và web security.

**Kết luận:** bốn công cụ không cạnh tranh nhau về một “thứ tự trước/sau” duy nhất. **Servlet Filter** ở ranh giới HTTP, **HandlerInterceptor** quanh MVC handler chain, **Spring AOP** quanh lời gọi method của bean qua proxy, còn **ControllerAdvice** gom logic MVC dùng chung như exception responses và binding/model customizations. Đặt cross-cutting logic ở tầng có đủ thông tin và đúng phạm vi, kiểm thử success/error/async và không thay Spring Security bằng một interceptor tùy biến.

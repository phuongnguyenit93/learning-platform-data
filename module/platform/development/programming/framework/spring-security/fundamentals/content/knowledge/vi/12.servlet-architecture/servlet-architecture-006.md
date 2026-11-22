# Quan hệ giữa bộ lọc bảo mật với MVC HandlerInterceptor

> **Chủ đề cha:** Kiến trúc Servlet · **Phạm vi:** Spring Security 6.x, Spring Framework MVC 6.x, Spring Boot 3.x, Java 17+ và Jakarta Servlet API. Bài học giải thích rõ vì sao **Spring Security hoạt động ở tầng Servlet Filter** còn **`HandlerInterceptor` thuộc tầng Spring MVC**; thứ tự khi request thành công, khi xác thực/phân quyền thất bại, khi interceptor ngăn handler, và ở các trường hợp `ERROR`/`ASYNC` dispatch. Có chương trình Java 17 minh họa trình tự gọi, một ứng dụng Spring Boot đủ các lớp và kiểm thử MockMvc. Không áp dụng nguyên xi sơ đồ Servlet này cho Spring WebFlux.

## 1. Hai lớp xử lý request, hai trách nhiệm khác nhau

Một HTTP request đi qua nhiều lớp trước khi tới `@RestController`. Trong ứng dụng Spring Boot Servlet với Spring Security, thường có hai vùng mở rộng dễ bị nhầm:

1. **Servlet Filter**, bao gồm filter chain của Spring Security: chạy trong **Servlet container**, bao ngoài `DispatcherServlet`; có thể xác thực, chống CSRF, xử lý session/security context và từ chối request trước khi MVC biết handler nào sẽ được gọi.
2. **MVC `HandlerInterceptor`**: do **Spring MVC `HandlerMapping`/`DispatcherServlet`** áp dụng cho `HandlerExecutionChain` đã được chọn; hữu ích cho ghi nhận thời gian xử lý handler, metadata request và các cross-cutting concerns gắn trực tiếp với MVC.

Sơ đồ cơ bản:

~~~text
Client
  |
  v
Servlet container
  |
  +--> Container Filters (nếu có)
  |
  +--> DelegatingFilterProxy
         |
         v
      FilterChainProxy (springSecurityFilterChain)
         |
         +--> SecurityFilterChain được chọn
                |
                +--> SecurityContextHolderFilter
                +--> CsrfFilter / CorsFilter / các exploit protections
                +--> Authentication filters
                +--> AnonymousAuthenticationFilter
                +--> ExceptionTranslationFilter
                +--> AuthorizationFilter
                |
                v
           DispatcherServlet
                |
                +--> HandlerMapping tìm handler
                |
                +--> HandlerInterceptor.preHandle(...)
                |
                +--> HandlerAdapter gọi Controller
                |
                +--> HandlerInterceptor.postHandle(...)
                |
                +--> HandlerInterceptor.afterCompletion(...)
                |
                v
           HTTP response
  |
  +--> Các Filter thực hiện phần sau chain.doFilter(...)
  |
  v
Client
~~~

Thứ tự trên chỉ là **mô hình khái niệm**, không phải danh sách đầy đủ các filter của mọi ứng dụng. Một filter có thể không chạy tùy `SecurityFilterChain`, cấu hình và dispatcher type. Nếu security filter từ chối request, đường đi có thể dừng **trước** `DispatcherServlet`, nên interceptor/controller sẽ không chạy.

**Câu nhớ nhanh:** *Servlet Filter đứng ngoài MVC; HandlerInterceptor nằm bên trong MVC*. Xác thực và phân quyền ở cửa ứng dụng nên dùng **Spring Security**, không thay thế bằng một interceptor kiểm tra header tùy ý.

## 2. Nhìn từ dưới lên: Filter và DispatcherServlet

### 2.1. `jakarta.servlet.Filter`

Servlet container xây dựng một `FilterChain` theo URL/dispatcher registration. Một filter có thể xử lý trước và sau thành phần kế tiếp:

~~~java
// Snippet trong một lớp triển khai jakarta.servlet.Filter.
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    before(request);
    try {
        chain.doFilter(request, response);
    } finally {
        after(request);
    }
}
~~~

`before`/`after` trong snippet là methods tự định nghĩa, không phải API của Servlet. Quan trọng là **`chain.doFilter` quyết định có chuyển request đi tiếp không**. Filter có thể chủ động trả response mà không gọi chain, từ đó `DispatcherServlet`, `HandlerMapping` và `HandlerInterceptor` không được gọi cho nhánh đó.

Servlet filters có thể chạy với:
- Request được MVC xử lý.
- Một servlet khác trong cùng container, nếu filter mapping bao phủ.
- Resource requests hoặc dispatch phù hợp.
- Những request bị chặn trước MVC.

Tuy nhiên một filter **không tự chạy cho mọi request trên thế giới**; nó phải được container đăng ký với URL/dispatcher mappings phù hợp. `OncePerRequestFilter` còn có quy tắc riêng cho async/error dispatch.

### 2.2. `DispatcherServlet`

`DispatcherServlet` là front controller của Spring MVC, nhận request sau những filter cho phép đi tiếp. Nó dùng `HandlerMapping` tìm handler, chẳng hạn method:

~~~java
@RestController
class BookController {

    @GetMapping("/books/{id}")
    String getBook(@PathVariable long id) {
        return "book:" + id;
    }
}
~~~

Đây là snippet minh họa MVC; chưa có bước bảo mật. Khi tìm được `HandlerExecutionChain`, MVC mới có cơ sở chạy những HandlerInterceptor áp dụng cho handler đó. Nếu một Servlet khác xử lý request, MVC interceptor sẽ không tự xen vào.

### 2.3. Không phải mọi request đều tới HandlerInterceptor

Các nhánh phổ biến mà MVC interceptor **có thể không chạy**:

- Spring Security từ chối username/password không hợp lệ, token không hợp lệ, thiếu role.
- `CsrfFilter` từ chối POST không có CSRF token hợp lệ.
- `CorsFilter` xử lý một preflight OPTIONS trước khi đến Controller.
- Một upstream Servlet Filter từ chối rate limit, request size hoặc header.
- Request được servlet khác xử lý, hoặc không được MVC `HandlerMapping` chọn một handler tương ứng.
- MVC interceptor không match path, bị exclude, hoặc không được đăng ký trên HandlerMapping thực tế.

**Chú ý về static resources:** Trong một ứng dụng Spring MVC, tài nguyên tĩnh có thể được `ResourceHttpRequestHandler` xử lý thông qua HandlerMapping. Vì thế không được khẳng định “mọi static resource luôn bỏ qua interceptor”. Hành vi phụ thuộc cách đăng ký resource handlers, filter/interceptor mappings và hạ tầng CDN/proxy.

## 3. Spring Security đi vào Servlet FilterChain ra sao?

Spring Security thường không đăng ký từng `CsrfFilter`, `AuthorizationFilter` và authentication filter độc lập với container. Thay vào đó:

~~~text
Servlet container
   |
   v
DelegatingFilterProxy
   |
   +--> Spring Bean: springSecurityFilterChain
             |
             v
        FilterChainProxy
             |
             +--> SecurityFilterChain #1, matcher /api/**
             +--> SecurityFilterChain #2, matcher còn lại
             |
             v
       Các filter trong chain đầu tiên match request
             |
             v
        DispatcherServlet (nếu không bị chặn)
~~~

### 3.1. `DelegatingFilterProxy`

`DelegatingFilterProxy` là cầu nối giữa Servlet container và bean do Spring quản lý. Bean target điển hình là `springSecurityFilterChain`, do `FilterChainProxy` đảm nhiệm. Nhờ đó Spring Security có thể dùng dependency injection, lifecycle và configuration của Spring.

Không nên nhầm:
- **Servlet container filter chain**: do container thiết lập.
- **Spring Security filter chain**: do `FilterChainProxy` chọn trong danh sách `SecurityFilterChain`.
- **MVC interceptor chain**: do Spring MVC `HandlerMapping` trả về cùng handler.

Ba chain này liên hệ nhau, nhưng không phải cùng một danh sách filter/interceptor.

### 3.2. `FilterChainProxy` và nhiều SecurityFilterChain

Nếu cấu hình:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(a -> a
        .anyRequest().denyAll());
    return http.build();
}
~~~

Đây là **snippet**, chưa có cơ chế authentication, nên không phải cấu hình hoàn chỉnh cho ứng dụng. Nó chỉ nhấn mạnh rằng `FilterChainProxy` **chọn chain đầu tiên khớp request**, không cộng tất cả filter của mọi chain lại.

- `/api/books` match chain API trước.
- `/books` match fallback chain.
- Nếu ứng dụng chỉ có chain `securityMatcher("/api/**")` và không có fallback, những URL khác **có thể nằm ngoài bảo vệ của Spring Security**.

MVC interceptor được đăng ký theo HandlerMapping, không tự biết một request đã match chain security nào. Vì vậy không dùng “có MVC interceptor” để bảo đảm mọi URL đều chịu security policy.

### 3.3. Các security filters làm gì trước MVC?

Một luồng thường có:
- `SecurityContextHolderFilter` nạp/chuẩn bị context cho request.
- CORS/CSRF và các exploit protections xử lý request theo cấu hình.
- Authentication filter (HTTP Basic, form login, Bearer token...) nhận credential.
- `AuthenticationManager`/provider xác minh danh tính.
- `AnonymousAuthenticationFilter` có thể tạo anonymous token.
- `ExceptionTranslationFilter` chuyển một số exception bảo mật thành hành vi HTTP.
- `AuthorizationFilter` kiểm tra rule `.permitAll()`, `.authenticated()`, `.hasRole()`...
- Sau khi pass, chain mới đưa request đến MVC.

**Không phải `HandlerInterceptor.preHandle()` là nơi bắt đầu xác thực.** Đến khi preHandle chạy, framework security thường đã nạp SecurityContext và có thể đã xác thực/cho phép request.

## 4. HandlerInterceptor thuộc Spring MVC

Interface `org.springframework.web.servlet.HandlerInterceptor` có ba callback:

~~~java
public interface HandlerInterceptor {

    default boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception {
        return true;
    }

    default void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            ModelAndView modelAndView) throws Exception {
    }

    default void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) throws Exception {
    }
}
~~~

Trên đây là **chữ ký rút gọn để học**, không phải file độc lập; interfaces/overrides còn phụ thuộc version. `HttpServletRequest`, `HttpServletResponse` đến từ **`jakarta.servlet.http`** với Spring Framework 6, không phải `javax.servlet.http` của stack cũ.

### 4.1. preHandle()

`preHandle` được gọi **trước handler** khi MVC đã tìm được handler. Nó trả:

- `true`: tiếp tục tới interceptor kế tiếp hoặc gọi handler.
- `false`: bỏ qua phần còn lại của `HandlerExecutionChain`; thông thường interceptor tự xử lý response hoặc đã có lý do dừng.

Ví dụ đúng mục đích MVC:

~~~java
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) {

    request.setAttribute(
        "mvc.startedAt", System.nanoTime()
    );
    return true;
}
~~~

Phần này đo thời điểm bắt đầu xử lý MVC handler, không xác minh mật khẩu/token.

### 4.2. postHandle()

`postHandle` chạy khi handler xử lý thành công và đường đi MVC phù hợp. Nó có thể quan sát `ModelAndView`, chỉnh model/view trong web MVC truyền thống.

~~~java
@Override
public void postHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        ModelAndView modelAndView) {
    // Metadata gắn với một MVC handler đã chạy.
}
~~~

**Cẩn thận với REST:** Với `@ResponseBody` hoặc `ResponseEntity`, response có thể đã được serialize/commit trong `HandlerAdapter` **trước** `postHandle`. Vì vậy `postHandle` thường **quá muộn** để chắc chắn thêm header hoặc thay response body. Dùng `ResponseBodyAdvice`, servlet filter hoặc thiết kế response rõ ràng khi cần tác động nội dung.

### 4.3. afterCompletion()

`afterCompletion` chạy khi MVC xử lý request hoàn tất theo lifecycle đồng bộ thông thường, và có thể nhận exception. Phù hợp để đo thời gian, dọn dữ liệu tạm MVC-scoped hoặc ghi metric.

~~~java
@Override
public void afterCompletion(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex) {

    Object started = request.getAttribute("mvc.startedAt");
    // Tính elapsed time nếu started hợp lệ.
}
~~~

**Không được giả định afterCompletion luôn chạy trong mọi nhánh.** Callback chỉ áp dụng cho những interceptors đã có `preHandle` hoàn tất thành công (true) trong execution chain. Nếu chính interceptor trả `false` ở `preHandle`, nó **không** nhận `afterCompletion` cho lần đó; những interceptor đứng trước đã trả true vẫn có thể nhận callback dọn dẹp. Với async request, callbacks khác biệt (phần dưới).

### 4.4. Nhiều interceptors có thứ tự ra sao?

Với hai interceptors A, B và controller:

~~~text
A.preHandle
B.preHandle
Controller
B.postHandle
A.postHandle
B.afterCompletion
A.afterCompletion
~~~

`preHandle` thường theo thứ tự đăng ký, còn `postHandle`/`afterCompletion` được gọi theo hướng ngược lại trong một execution chain. Nếu `B.preHandle` trả false, Controller và `postHandle` đều không chạy; chỉ `A.afterCompletion` được gọi cho phần đã bắt đầu thành công.

Spring Security filter bao ngoài tất cả callbacks đó. Nếu filter có phần trước/sau `chain.doFilter`, chúng có thể ôm lấy toàn bộ lifecycle MVC đồng bộ:

~~~text
Security Filter BEFORE
  A.pre
    B.pre
      Controller
    B.post
  A.post
    B.after
  A.after
Security Filter AFTER
~~~

Đây là sơ đồ để hiểu thứ tự; thứ tự chính xác của filter và callbacks khác nhau ở async, error/forward dispatch hoặc khi response bị chặn.

## 5. So sánh trực tiếp Filter và HandlerInterceptor

| Tiêu chí | Servlet Filter / Spring Security Filter | MVC HandlerInterceptor |
| --- | --- | --- |
| Tầng | Servlet container, trước/trong vòng bao của servlet | Spring MVC HandlerExecutionChain |
| Biết `@GetMapping` handler? | Không tự biết handler đã chọn | Có `Object handler`, thường có `HandlerMethod` |
| Có thể chặn trước MVC? | **Có** | Không, vì chỉ chạy khi đã vào MVC |
| Phạm vi | Theo filter registration, SecurityFilterChain matcher và dispatcher type | Theo HandlerMapping/InterceptorRegistry/path patterns |
| Cơ chế vào chuỗi | `doFilter` / `chain.doFilter` | `preHandle`, `postHandle`, `afterCompletion` |
| Xác thực credentials | Security filters/providers | Không nên thay thế cơ chế framework |
| Phân quyền URL | `AuthorizationFilter`/`AuthorizationManager` | Không nên là hàng rào chính |
| CSRF, CORS, SecurityContext | Có filter/framework integration chuyên dụng | Không phù hợp làm lớp thay thế |
| Ghi metric MVC handler | Có thể ghi request-level metrics | Rất phù hợp ghi handler-level metadata |
| Request bị security từ chối | Có thể thấy hoặc xử lý trong security/filter layer, tùy vị trí | **Thường không chạy** |
| Static resources/other servlets | Có thể bao phủ theo registration | Chỉ khi được MVC HandlerMapping xử lý |
| Async/error handling | Theo Servlet dispatcher + filter rules | Theo MVC async/interceptor lifecycle |
| Việc thêm header | Filter đúng thời điểm trước response commit | `postHandle` có thể quá muộn với REST |

**Không phải Filter luôn tốt hơn Interceptor.** Chúng giải quyết các bài toán khác nhau. Với tracking tên controller handler, interceptor được thiết kế rất phù hợp. Với xác thực và phân quyền, Spring Security filter chain và method security là những điểm được thiết kế riêng, có khả năng bao phủ rộng và xử lý sớm hơn.

## 6. Tại sao không nên làm authentication trong HandlerInterceptor?

Một anti-pattern hay gặp:

~~~java
// KHÔNG dùng làm lớp xác thực chính của ứng dụng.
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) {

    String apiKey = request.getHeader("X-API-Key");

    if (!"hard-coded-secret".equals(apiKey)) {
        response.setStatus(401);
        return false;
    }
    return true;
}
~~~

Đoạn này có hàng loạt vấn đề:

1. Interceptor chỉ chạy cho các handlers mà MVC mapping bao phủ; request bị xử lý bởi servlet khác hoặc đường đi không match có thể bỏ qua nó.
2. Hard-coded secret không có cơ chế key rotation, replay protection, scope, issuer, expiry hoặc audit.
3. Nó không tích hợp đúng `AuthenticationManager`, `SecurityContextHolder` và error handling của Spring Security.
4. Nếu path patterns giữa security endpoint và MVC interceptor không khớp, một route mới có thể bị bỏ sót.
5. CORS preflight, CSRF và authentication failures có thể xảy ra trước interceptor.
6. Thêm interceptor không tự bảo vệ `@Service`, `@Scheduled` hoặc code được gọi ngoài MVC.

Spring Framework cũng nhấn mạnh **MVC interceptors không phải lớp bảo mật lý tưởng**, vì có thể lệch giữa interceptor path matching và controller annotation mapping. Hãy dùng Spring Security hoặc cơ chế bảo mật tích hợp ở Servlet filter layer.

### 6.1. Vậy HandlerInterceptor có thể đọc SecurityContext không?

**Có.** Khi request đã đi qua security filters và vào MVC:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Interceptor có thể đọc `getName()`, authorities hoặc principal type để phục vụ log/tracing có giới hạn. Nhưng:

- `auth == null` có thể xảy ra theo cấu hình hoặc nơi chạy.
- `AnonymousAuthenticationToken` có thể báo `isAuthenticated()==true`.
- Không nên log full Authentication, credentials hoặc JWT.
- `getAuthorities()` có thể là snapshot quyền đã cũ; không thay kiểm tra role/ownership ở điểm xử lý nghiệp vụ.
- Chỉ việc đọc context không làm interceptor trở thành một authentication provider.

### 6.2. Nếu cần quyền theo tài nguyên?

Dùng URL rules của Spring Security kết hợp **method security** và domain authorization. Ví dụ:

~~~java
// Snippet: cần @EnableMethodSecurity và documentPolicy bean thật.
@PreAuthorize(
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentDto loadDocument(long documentId) {
    return repository.load(documentId);
}
~~~

Code trên **không độc lập để biên dịch**: `DocumentDto`, `repository` và `documentPolicy` phải do project triển khai. Ý tưởng quan trọng là policy kiểm tra `Authentication` đáng tin, resource ID, owner/tenant/permissions hiện hành, không chỉ header tùy ý hay role tĩnh tại MVC interceptor.

### 6.3. Security filter và MethodInterceptor không phải MVC HandlerInterceptor

Trong Spring Security có thuật ngữ như `AuthorizationManagerBeforeMethodInterceptor`. Đó là interceptor phục vụ **Spring Method Security/AOP**, không phải `org.springframework.web.servlet.HandlerInterceptor`. Tên giống nhau nhưng tầng hoạt động khác. Một `@PreAuthorize` trên service có thể bảo vệ method dù caller không đến từ một MVC controller, miễn method security được cấu hình và lời gọi đi qua proxy thích hợp.

## 7. Khi request thất bại trước MVC: 401, 403 và không có preHandle

Giả sử có một endpoint `/admin/panel` yêu cầu ROLE_ADMIN:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

Với một Spring Security chain có HTTP Basic:

| Request | Đi được đến MVC? | Kết quả phổ biến |
| --- | --- | --- |
| Anonymous `GET /admin/panel` | Không | `401` từ Basic AuthenticationEntryPoint |
| Alice đã xác thực, chỉ có ROLE_USER | Không | `403` từ authorization |
| Admin có ROLE_ADMIN | Có | Controller chạy, interceptors chạy |
| POST thiếu CSRF hợp lệ khi CSRF bật | Thường không | `403` do CSRF, ngay cả khi admin |
| Public `GET /public/ping` | Có | `200`, interceptors có thể chạy |
| `OPTIONS` preflight được CORS xử lý sớm | Có thể không | Trạng thái tùy CORS filter config |

**Một assertion `preHandle()` không chạy không đủ phân biệt lý do.** Phải xác định filter nào trả response: CSRF, authentication, authorization, CORS, một custom filter hay proxy phía trước.

### 7.1. 401 khác 403

- `401 Unauthorized`: request chưa có credential hợp lệ hoặc cần authentication; Basic thường trả `WWW-Authenticate`.
- `403 Forbidden`: request đã xác thực nhưng thiếu quyền, hoặc bị một protection khác như CSRF từ chối.
- Với form login, thiếu authentication có thể trả redirect `302` thay vì 401.
- Với custom entry point/AccessDeniedHandler, body/status có thể khác.

`HandlerInterceptor` không mặc định thực thi sau những phản hồi ở tầng security. Muốn quan sát **tất cả** trường hợp, phải dùng logging ở security filters/authorization events hoặc request-level instrumentation được đăng ký sớm đúng phạm vi, không chỉ log ở preHandle.

## 8. Chương trình Java 17 độc lập: tại sao “trước–sau” lồng nhau?

Để hiểu call stack của filter và interceptor mà không cần Spring, tạo `CallOrderLab.java`:

~~~java
public class CallOrderLab {

    public static void main(String[] args) {
        servletFilter(() ->
            mvcInterceptor(() ->
                controller()
            )
        );
    }

    static void servletFilter(Runnable next) {
        System.out.println("filter.before");
        try {
            next.run();
        } finally {
            System.out.println("filter.after");
        }
    }

    static void mvcInterceptor(Runnable handler) {
        System.out.println("mvc.pre");
        try {
            handler.run();
            System.out.println("mvc.post");
        } finally {
            System.out.println("mvc.after");
        }
    }

    static void controller() {
        System.out.println("controller");
    }
}
~~~

Lệnh chạy:

~~~bash
javac CallOrderLab.java
java CallOrderLab
~~~

**Stdout chính xác:**

~~~text
filter.before
mvc.pre
controller
mvc.post
mvc.after
filter.after
~~~

Đây là **mô hình thuần Java** về lời gọi lồng nhau, không phải source code thực tế của Spring Security hoặc `HandlerExecutionChain`. Nó chưa mô phỏng `preHandle(false)`, error handling và async dispatch. Phần Spring Boot dưới đây sẽ dùng `OncePerRequestFilter` và `HandlerInterceptor` thật để kiểm tra thứ tự thực tế.

## 9. Ứng dụng Spring Boot 3: filter bảo mật và MVC interceptor cùng chạy

Mục tiêu của demo:

1. Spring Security xác thực bằng HTTP Basic với hai account mẫu: Alice ROLE_USER và admin ROLE_ADMIN.
2. `AuthorizationFilter` kiểm tra route trước khi MVC được phép xử lý.
3. Một **custom filter chỉ ghi trace** được gắn **sau `AuthorizationFilter`** bên trong `SecurityFilterChain`.
4. Một MVC `TraceInterceptor` ghi thứ tự `preHandle`, `postHandle`, `afterCompletion`.
5. Một MVC `BlockInterceptor` trả `false` ở `preHandle`, chặn một controller demo nhưng **không giả làm security layer**.
6. Controller ghi dấu vào request attribute để test đối chiếu callback.
7. MockMvc chứng minh request thành công có cả filter+interceptor; request không đủ quyền bị security từ chối trước khi interceptor chạy; POST thiếu CSRF bị chặn trước MVC.

**Giới hạn demo:** Chỉ ghi trace của các synchronous MVC methods. Không dùng trace filter này để bảo đảm thu thập mọi 401/403 hay logging production. Không tạo một authentication filter tùy biến, không tắt CSRF và không đưa credentials thật vào code.

### 9.1. Dependencies và cấu trúc file

Tạo Spring Boot 3.x (Spring Framework 6.x, Spring Security 6.x), Java 17+, Gradle Wrapper/plugin đã cấu hình. Thêm dependencies vào `build.gradle` hiện có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây chỉ là dependencies, **không phải toàn bộ build.gradle**. Các files:

~~~text
src/main/java/com/example/mvcfilter/
  MvcFilterApplication.java
  SecurityConfig.java
  TraceEvents.java
  RequestTraceFilter.java
  TraceInterceptor.java
  BlockInterceptor.java
  MvcConfig.java
  DemoController.java

src/test/java/com/example/mvcfilter/
  FilterAndInterceptorTest.java
~~~

### 9.2. MvcFilterApplication.java

~~~java
package com.example.mvcfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcFilterApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcFilterApplication.class, args);
    }
}
~~~

### 9.3. TraceEvents.java — lưu dấu theo từng request

~~~java
package com.example.mvcfilter;

import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;

public final class TraceEvents {

    public static final String KEY =
        TraceEvents.class.getName() + ".events";

    public static final String MVC_PRINCIPAL =
        TraceEvents.class.getName() + ".mvcPrincipal";

    private TraceEvents() {}

    @SuppressWarnings("unchecked")
    public static List<String> events(
            HttpServletRequest request) {

        Object existing = request.getAttribute(KEY);

        if (existing instanceof List<?>) {
            return (List<String>) existing;
        }

        List<String> created = new ArrayList<>();
        request.setAttribute(KEY, created);
        return created;
    }

    public static void add(
            HttpServletRequest request, String event) {
        events(request).add(event);
    }
}
~~~

Tất cả trace được giữ trong **request attribute**, không lưu static mutable list dùng chung cho mọi người. `KEY` là tên attribute không phải credential. Với demo synchronous, `ArrayList` đủ dùng. Nếu biến bài này thành async/concurrent instrumentation, cần một cấu trúc thread-safe hoặc event sink khác và phải xử lý dispatcher semantics.

### 9.4. RequestTraceFilter.java — chỉ là diagnostic filter

~~~java
package com.example.mvcfilter;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class RequestTraceFilter
        extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        TraceEvents.add(
            request, "security.filter.before"
        );

        try {
            chain.doFilter(request, response);
        } finally {
            TraceEvents.add(
                request, "security.filter.after"
            );
        }
    }
}
~~~

`OncePerRequestFilter` giúp tránh một số trường hợp chạy lặp trong một dispatch theo framework contract. Nhưng đừng hiểu tên của nó là **chính xác một lần cho toàn bộ HTTP logical request qua mọi `ASYNC`/`ERROR` dispatch**; có các hooks như `shouldNotFilterAsyncDispatch` và `shouldNotFilterErrorDispatch` cần xem theo thực tế.

**Không gắn `@Component` vào class filter này**, vì trong demo ta thêm **một instance trực tiếp vào Spring Security chain**. Nếu vừa đăng ký như container `Filter` bean vừa `.addFilterAfter` vào `HttpSecurity`, có nguy cơ filter bị đăng ký/chạy hai lần hoặc ở hai vị trí thứ tự khác nhau.

### 9.5. TraceInterceptor.java — callback của MVC

~~~java
package com.example.mvcfilter;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.lang.Nullable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

public class TraceInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        TraceEvents.add(request, "mvc.pre");

        Authentication authentication =
            SecurityContextHolder.getContext()
                .getAuthentication();

        request.setAttribute(
            TraceEvents.MVC_PRINCIPAL,
            authentication == null
                ? "none"
                : authentication.getName()
        );

        return true;
    }

    @Override
    public void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            @Nullable ModelAndView modelAndView) {

        TraceEvents.add(request, "mvc.post");
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {

        TraceEvents.add(request, "mvc.after");
    }
}
~~~

`@Nullable` ở import chỉ để chú thích tham số `ModelAndView` có thể null, **không cần thiết cho phép biên dịch**; trong Spring Framework 6.x có thể bỏ annotation/import mà không thay behavior. Interceptor này không quyết định quyền; nó chỉ ghi trace và principal name đã được Spring Security thiết lập.

**Không dùng raw `authentication.isAuthenticated()` làm điều kiện bảo mật custom**, vì anonymous token có thể có flag true. Luật `.authenticated()` của Spring Security phân biệt anonymous bằng cơ chế framework.

### 9.6. BlockInterceptor.java — minh họa preHandle(false)

~~~java
package com.example.mvcfilter;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.servlet.HandlerInterceptor;

public class BlockInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception {

        TraceEvents.add(request, "mvc.block");
        response.setStatus(418);
        response.getWriter().write("blocked-by-mvc");
        return false;
    }
}
~~~

`418` ở đây là **mã demo có chủ đích để phân biệt MVC stop với lỗi security**, không phải status nên dùng cho authorization production. Interceptor chỉ dừng method handler của MVC tương ứng. Nó **không phải cơ chế xác thực**.

### 9.7. MvcConfig.java — đăng ký MVC interceptors đúng tầng

~~~java
package com.example.mvcfilter;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {

        registry.addInterceptor(new TraceInterceptor())
            .addPathPatterns("/**");

        registry.addInterceptor(new BlockInterceptor())
            .addPathPatterns("/public/blocked");
    }
}
~~~

`TraceInterceptor` được đăng ký trước nên trên `/public/blocked`, nó đã trả `true` ở preHandle, sau đó `BlockInterceptor` trả `false`. MVC không gọi controller, không gọi `postHandle`, nhưng gọi `TraceInterceptor.afterCompletion` vì interceptor này đã preHandle thành công.

Đây là thứ tự của MVC interceptors, **không phải vị trí trong Spring Security FilterChainProxy**. `InterceptorRegistry` path patterns không tự trở thành `RequestMatcher` của security DSL.

### 9.8. SecurityConfig.java — authentication/authorization xảy ra trước MVC

~~~java
package com.example.mvcfilter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/user/profile")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin/panel")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/admin/rebuild")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .addFilterAfter(
                new RequestTraceFilter(),
                AuthorizationFilter.class
            );

        return http.build();
    }
}
~~~

Đọc chậm từng điểm:

- HTTP Basic xác thực credential mỗi request trong ví dụ stateless; `PasswordEncoder` dùng BCrypt.
- `/public/**` cho phép anonymous. Filter chain vẫn chạy với `permitAll`; không dùng `web.ignoring()`.
- `/user/profile` yêu cầu user authenticated.
- `/admin/panel` và `/admin/rebuild` cần `ROLE_ADMIN`.
- `anyRequest().denyAll()` chặn endpoint/method chưa được liệt kê.
- `CsrfFilter` **vẫn bật** theo cấu hình mặc định. Vì POST `/admin/rebuild` là state-changing request, test phải gửi CSRF token.
- `RequestTraceFilter` được gắn **sau `AuthorizationFilter`**, nghĩa là **chỉ những request vượt qua authorization** mới đi tới filter trace này. Vì vậy 401/403 từ các security filters trước đó **không nhất thiết có** trace event.
- Trong Spring Security, authentication/CSRF/authorization filters có thứ tự riêng. `.addFilterAfter` chọn điểm chèn **tương đối với một class filter**, không có ý nghĩa “sau tất cả các Servlet Filters của container”.

**Bài học về instrumenting:** Nếu muốn log **cả 401/403** hoặc đo full request latency, đặt instrumentation ở vị trí sớm hơn/đúng công cụ, ví dụ filter ở Servlet container hoặc security-specific events, chứ không chỉ đặt một filter sau `AuthorizationFilter`.

### 9.9. DemoController.java

~~~java
package com.example.mvcfilter;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping(HttpServletRequest request) {
        TraceEvents.add(request, "controller");
        return "pong";
    }

    @GetMapping("/public/blocked")
    public String blocked(HttpServletRequest request) {
        TraceEvents.add(request, "controller");
        return "should-not-run";
    }

    @GetMapping("/user/profile")
    public String profile(
            HttpServletRequest request,
            Authentication authentication) {

        TraceEvents.add(request, "controller");
        return "user:" + authentication.getName();
    }

    @GetMapping("/admin/panel")
    public String panel(HttpServletRequest request) {
        TraceEvents.add(request, "controller");
        return "admin-panel";
    }

    @PostMapping("/admin/rebuild")
    public String rebuild(HttpServletRequest request) {
        TraceEvents.add(request, "controller");
        return "rebuild-accepted";
    }
}
~~~

Controller xử lý nghiệp vụ sau khi SecurityFilterChain đã cho phép request. `Authentication` từ Spring MVC injection ở endpoint protected được dùng để lấy name, **không sử dụng password/secret**. Code chỉ ghi string `"controller"` vào request attribute để quan sát call order.

### 9.10. Chạy và thử bằng curl

Từ thư mục root có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Thử trong localhost:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/public/blocked
curl -i http://localhost:8080/user/profile
curl -i -u alice:alice123 http://localhost:8080/user/profile
curl -i -u alice:alice123 http://localhost:8080/admin/panel
curl -i -u admin:admin123 http://localhost:8080/admin/panel
curl -i -u admin:admin123 -X POST http://localhost:8080/admin/rebuild
~~~

Kỳ vọng:

| Request | HTTP status | Body/ý nghĩa |
| --- | --- | --- |
| GET `/public/ping`, anonymous | 200 | `pong`, MVC đã chạy |
| GET `/public/blocked`, anonymous | 418 | `blocked-by-mvc`, controller không chạy |
| GET `/user/profile`, anonymous | 401 | Security yêu cầu Basic auth trước MVC |
| GET `/user/profile`, Basic Alice | 200 | `user:alice` |
| GET `/admin/panel`, Basic Alice | 403 | Alice thiếu ROLE_ADMIN; interceptor không chạy |
| GET `/admin/panel`, Basic admin | 200 | `admin-panel` |
| POST `/admin/rebuild`, Basic admin, **không CSRF token** | 403 | CsrfFilter chặn, không phải thiếu ROLE_ADMIN |

**Đừng tắt CSRF để POST “được 200”.** Với browser/session authentication, CSRF là bảo vệ quan trọng; ngay cả demo Basic này vẫn để CSRF bật để học rõ filter-level denial. Test tiếp theo dùng `.with(csrf())` để tạo một POST hợp lệ.

**Không dùng `curl -u` với mật khẩu thật trên máy dùng chung**, vì command history/process args có thể lộ credentials. Mã mẫu dành cho localhost, dùng TLS và secret handling phù hợp ở production.

## 10. MockMvc test: chứng minh thứ tự và chỗ request bị chặn

Tạo file `src/test/java/com/example/mvcfilter/FilterAndInterceptorTest.java`:

~~~java
package com.example.mvcfilter;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterAndInterceptorTest {

    @Autowired
    MockMvc mvc;

    private List<String> trace(MvcResult result) {
        Object attribute =
            result.getRequest().getAttribute(TraceEvents.KEY);

        if (!(attribute instanceof List<?> list)) {
            return List.of();
        }
        return list.stream()
            .map(String::valueOf)
            .toList();
    }

    private List<String> normalOrder() {
        return List.of(
            "security.filter.before",
            "mvc.pre",
            "controller",
            "mvc.post",
            "mvc.after",
            "security.filter.after"
        );
    }

    @Test
    void successfulMvcRequestRunsFilterAroundInterceptor()
            throws Exception {

        MvcResult result = mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"))
            .andReturn();

        assertEquals(normalOrder(), trace(result));
    }

    @Test
    void authenticatedRequestRunsMvcWithTrustedPrincipal()
            throws Exception {

        MvcResult result = mvc.perform(get("/user/profile")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("user:alice"))
            .andReturn();

        assertEquals(normalOrder(), trace(result));
        assertEquals(
            "alice",
            result.getRequest()
                .getAttribute(TraceEvents.MVC_PRINCIPAL)
        );
    }

    @Test
    void anonymousIsRejectedBeforeMvcInterceptor()
            throws Exception {

        MvcResult result = mvc.perform(get("/user/profile"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        assertNull(
            result.getRequest().getAttribute(TraceEvents.KEY)
        );
    }

    @Test
    void insufficientRoleIsRejectedBeforeMvcInterceptor()
            throws Exception {

        MvcResult result = mvc.perform(get("/admin/panel")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden())
            .andReturn();

        assertNull(
            result.getRequest().getAttribute(TraceEvents.KEY)
        );
    }

    @Test
    void adminRoleAllowsControllerAndMvcCallbacks()
            throws Exception {

        MvcResult result = mvc.perform(get("/admin/panel")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-panel"))
            .andReturn();

        assertEquals(normalOrder(), trace(result));
        assertEquals(
            "admin",
            result.getRequest()
                .getAttribute(TraceEvents.MVC_PRINCIPAL)
        );
    }

    @Test
    void preHandleFalseStopsControllerButOuterFilterFinishes()
            throws Exception {

        MvcResult result = mvc.perform(get("/public/blocked"))
            .andExpect(status().is(418))
            .andExpect(content().string("blocked-by-mvc"))
            .andReturn();

        assertEquals(
            List.of(
                "security.filter.before",
                "mvc.pre",
                "mvc.block",
                "mvc.after",
                "security.filter.after"
            ),
            trace(result)
        );
    }

    @Test
    void csrfRejectionHappensBeforeMvcEvenForAdmin()
            throws Exception {

        MvcResult result = mvc.perform(post("/admin/rebuild")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden())
            .andReturn();

        assertNull(
            result.getRequest().getAttribute(TraceEvents.KEY)
        );
    }

    @Test
    void validCsrfAndAdminRolePermitPost()
            throws Exception {

        MvcResult result = mvc.perform(post("/admin/rebuild")
                .with(httpBasic("admin", "admin123"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("rebuild-accepted"))
            .andReturn();

        assertEquals(normalOrder(), trace(result));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

### 10.1. Đọc test `successfulMvcRequestRunsFilterAroundInterceptor`

Sáu event dự kiến:

~~~text
security.filter.before
mvc.pre
controller
mvc.post
mvc.after
security.filter.after
~~~

Đây là **thứ tự callback đồng bộ dự kiến** trên một request được security permit, HandlerMapping tìm được handler và không phát sinh exception/async. Dòng filter after ở cuối vì mã filter gọi `chain.doFilter` rồi mới chạy `finally`.

### 10.2. Test 401/403 chứng minh điều gì?

`anonymousIsRejectedBeforeMvcInterceptor` và `insufficientRoleIsRejectedBeforeMvcInterceptor` kiểm tra `TraceEvents.KEY == null`.

Trong **cấu hình demo**, custom RequestTraceFilter được đặt sau AuthorizationFilter, và MVC TraceInterceptor chỉ chạy khi request được MVC xử lý. Vì vậy:
- Nếu authentication entry point chặn 401 hoặc AuthorizationFilter từ chối 403, chưa có event.
- Không được suy ra **không có Servlet Filter nào chạy**! Rất nhiều security filters trước đó đã chạy để ra quyết định.
- Nếu đặt custom filter ở một vị trí khác, kết quả trace sẽ khác.

### 10.3. preHandle(false) và afterCompletion

TraceInterceptor đứng trước BlockInterceptor. Trace preHandle trả true, Block preHandle trả false. Controller **không chạy**, hai `postHandle` không chạy; Trace afterCompletion vẫn chạy, filter finally vẫn chạy. Đây là lý do test không kỳ vọng `"controller"` hoặc `"mvc.post"` trong nhánh bị block.

**BlockInterceptor tự nó không nhận afterCompletion** trong nhánh preHandle=false; nếu muốn thu dọn resources đã tạo trong preHandle của chính interceptor chặn, phải tự đảm bảo cleanup trước khi trả false.

### 10.4. POST không có CSRF khác thiếu role

`csrfRejectionHappensBeforeMvcEvenForAdmin` dùng đúng username/password của admin nhưng không gửi CSRF token; vì mặc định CSRF protection được bật cho unsafe methods, request bị 403. Test `validCsrfAndAdminRolePermitPost` bổ sung `.with(csrf())` để có request hợp lệ; sau đó mọi callback theo order mới chạy.

Hai test này giúp phân biệt:
- Authentication đã thành công.
- Authorization có thể cho phép ROLE_ADMIN.
- Nhưng **CSRF protection** là một kiểm tra khác ở filter layer, có thể từ chối trước MVC.

**Những kết quả trên là assertions kỳ vọng theo mã ví dụ, không phải báo cáo đã chạy Gradle trong môi trường này.** Phiên bản Spring Boot/Security, filter dispatcher registration hoặc custom exception handling khác có thể yêu cầu điều chỉnh tests.

## 11. Khi nào preHandle, postHandle, afterCompletion KHÔNG chạy?

### 11.1. preHandle không chạy

Các lý do thường gặp:
- Request đã bị security filter từ chối.
- CORS preflight được xử lý trước DispatcherServlet.
- Request do Servlet khác xử lý.
- MVC HandlerMapping không chọn handler được interceptor áp dụng, hoặc path bị exclude.
- MVC request bị dừng bởi interceptor đứng trước.
- Có response do upstream filter tạo trước MVC.

Không tự kết luận “interceptor bị lỗi registration” nếu request 401 trước đó.

### 11.2. postHandle không chạy

Có thể vì:
- Một interceptor trả false ở preHandle.
- Controller ném exception và luồng đi vào error resolution.
- MVC async processing bắt đầu và xử lý callback khác ở dispatch đầu.
- Các điều kiện framework/response đã kết thúc sớm.

Ngay cả khi postHandle chạy với REST, response body có thể đã được xử lý. Đừng sử dụng `postHandle` làm điểm duy nhất để sửa JSON của `@ResponseBody`.

### 11.3. afterCompletion không chạy ở interceptor chưa preHandle thành công

`HandlerExecutionChain` chỉ áp callback dọn cho những interceptors đã vượt qua preHandle thành công. Khi một interceptor trả false, MVC gọi `afterCompletion` cho các interceptor **đứng trước** đã trả true. Các interceptors còn lại chưa chạy thì không có callback hoàn tất.

Nếu cần đo thời gian toàn bộ HTTP request, bao gồm cả request bị security từ chối, instrumentation ở Servlet filter layer phù hợp hơn chỉ đo trong `afterCompletion`.

### 11.4. ExceptionTranslationFilter và ngoại lệ từ MVC

`ExceptionTranslationFilter` có thể chuyển các exception bảo mật phát sinh downstream thành HTTP response theo entry point/handler khi chúng đến được nó. Nhưng **đừng dựa vào interceptor ném một exception tự chế rồi mặc định luôn được xử lý như `AccessDeniedException`**. Spring MVC có thể bắt/resolve exception qua `HandlerExceptionResolver`; phải hiểu loại exception và nơi catch.

Một interceptor ghi log `postHandle` có thể bỏ lỡ request ném exception, trong khi filter dùng `try/finally` vẫn có thể ghi phần after nếu invocation đã vào filter và trả/throw về upstream.

## 12. Async, ERROR/FORWARD dispatch và những ngoại lệ của sơ đồ

Sơ đồ synchronous ở đầu bài là nền tảng, nhưng ứng dụng thực tế có async, forward và error dispatch.

### 12.1. MVC AsyncHandlerInterceptor

`AsyncHandlerInterceptor` mở rộng `HandlerInterceptor` để có thêm `afterConcurrentHandlingStarted`. Với async request, ví dụ controller trả `Callable`, `DeferredResult` hoặc `CompletableFuture`, trình tự callback có thể là:

~~~text
REQUEST dispatch:
  preHandle
  Controller bắt đầu async
  afterConcurrentHandlingStarted  (nếu interceptor hỗ trợ)
  -> Servlet thread trở lại container

ASYNC dispatch khi có kết quả:
  preHandle có thể được gọi lại
  Xử lý kết quả
  postHandle
  afterCompletion
~~~

Không được assume `postHandle` và `afterCompletion` xảy ra ngay trên initial dispatch. Một interceptor có state trong ThreadLocal cần dọn đúng ở nhánh async, nếu không có thể gây leak khi servlet thread quay lại pool. Dùng request attributes/tracing library có async support nếu cần correlation.

### 12.2. OncePerRequestFilter và dispatcher types

Một `OncePerRequestFilter` có hooks như:
- `shouldNotFilterAsyncDispatch()`
- `shouldNotFilterErrorDispatch()`
- `shouldNotFilter(request)`

Hành vi phụ thuộc dispatch registration và flags. **“Once per request” không phải bảo đảm một lần cho toàn bộ lifecycle logic khi request có nhiều dispatch**. Filter instrumentation có thể cần ghi một event ở initial request và event khác ở async/error dispatch tùy mục tiêu.

### 12.3. FORWARD và ERROR có thể chạy authorization thêm lần nữa

Spring Security `AuthorizationFilter` có thể đánh giá nhiều dispatcher types; `FORWARD` tới view hoặc `ERROR` tới error endpoint có thể phát sinh một authorization decision khác. Nếu cấu hình default deny mà không xét dispatch, có thể gặp 403 ở error page hoặc view.

Với policy phù hợp, có thể cân nhắc:

~~~java
// Snippet minh họa, không phải rule nên bật tùy tiện.
http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.FORWARD,
        DispatcherType.ERROR
    ).permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Cần import `jakarta.servlet.DispatcherType`. Việc `permitAll` cho toàn bộ FORWARD/ERROR **là lựa chọn chính sách có đánh đổi**, chỉ dùng nếu ứng dụng thực sự cần và các endpoint nội bộ đã được kiểm soát. Không copy rồi mặc định mọi forward sẽ an toàn. Quan sát đồng thời behavior của security filter chain, MVC interceptor và dispatcher registrations.

### 12.4. CORS preflight

Browser thường gửi một preflight `OPTIONS` trước cross-origin request. Preflight có thể không có session cookie/Authorization của request chính. Nếu Security yêu cầu authentication **trước khi xử lý CORS**, browser có thể bị chặn sai.

Spring Security hỗ trợ CORS integration ở filter layer, ví dụ:

~~~java
http.cors(Customizer.withDefaults());
~~~

Đây là snippet, cần một `CorsConfigurationSource` hoặc MVC CORS configuration phù hợp và policy allowlist origins/methods/headers. **Không coi MVC interceptor là giải pháp CORS preflight**. Không dùng wildcard origin cùng credentials một cách tùy tiện.

### 12.5. CSRF

`CsrfFilter` bảo vệ state-changing requests khi policy cần CSRF, trước khi MVC handler chạy. Một interceptor dùng để kiểm tra “admin” không thay thế CSRF. Nếu browser dùng session cookies, phải giữ CSRF phù hợp cho POST/PUT/PATCH/DELETE hoặc có threat model khác được đánh giá rõ.

### 12.6. Không áp dụng Servlet sơ đồ cho WebFlux

Spring WebFlux dùng `WebFilter`, `SecurityWebFilterChain`, `WebFilterChain` và `DispatcherHandler` thay vì Servlet Filter/DispatcherServlet MVC. Reactive Security Context đi qua Reactor Context. Không tự đổi tên `HandlerInterceptor` thành WebFlux interceptor hay áp `ThreadLocal` Servlet vào reactive pipeline.

## 13. Đặt logic ở đâu cho đúng?

| Yêu cầu | Lớp phù hợp | Lý do |
| --- | --- | --- |
| Username/password, Bearer JWT hoặc opaque token | Spring Security authentication filters/providers | Xác minh trước Controller, tích hợp SecurityContext |
| Kiểm tra ROLE_ADMIN với URL | `authorizeHttpRequests`/AuthorizationFilter | Tránh để MVC handler được gọi khi không có quyền |
| Cấp quyền `readInvoice` theo owner/tenant | Method security/domain policy | Kiểm tra tài nguyên và caller, không chỉ URL |
| CSRF, CORS, secure headers | Security filters và filter-based integrations | Xử lý sớm trước MVC |
| Rate limiting toàn ứng dụng | Gateway hoặc Servlet Filter/infrastructure | Bao phủ request không được MVC xử lý |
| Ghi metadata tên controller/handler mapping | MVC HandlerInterceptor | Có `Object handler`, có thể dùng HandlerMethod |
| Đo thời gian chỉ xử lý MVC handler | HandlerInterceptor + metrics phù hợp | Bắt đầu sau khi HandlerMapping chọn handler |
| Đo end-to-end HTTP latency kể cả 401/403 | Servlet Filter/observability framework sớm | MVC interceptor có thể không chạy |
| Tùy biến JSON response body | `ResponseBodyAdvice` | Chạy ở nơi response body được xử lý |
| Chuyển exception nghiệp vụ sang status | `@ControllerAdvice`/HandlerExceptionResolver | MVC exception handling |
| Chuyển authentication/authorization failures | AuthenticationEntryPoint/AccessDeniedHandler | Spring Security có cơ chế chuyên dụng |
| Logging cho `@Scheduled` hoặc queue consumer | Job instrumentation/service layer | Không có MVC request/HandlerInterceptor |
| Authorization service gọi ngoài HTTP | Method security/service guard | Không phụ thuộc MVC entrypoint |

Không cố gom tất cả cross-cutting logic vào một lớp interceptor. Nhiều lớp có trách nhiệm riêng giúp dễ kiểm thử và tránh lỗ hổng do lệch phạm vi matching.

### 13.1. Một ví dụ ownership

Endpoint:

~~~java
@GetMapping("/documents/{id}")
DocumentDto readDocument(@PathVariable long id) {
    return documentService.readDocument(id);
}
~~~

Security DSL có thể yêu cầu `.authenticated()` cho `/documents/**`. Nhưng quyền “được đọc document id=123” phải do `documentService` hoặc policy bean kiểm tra owner/tenant/ACL, có thể dùng method security.

Nếu dùng MVC interceptor để check `X-User-Id` và `X-Document-Owner`, attacker có thể giả header; path alias, servlet routes, async calls và service invocation cũng có thể bỏ qua. Identity phải lấy từ Authentication được xác minh; quyền phải dựa vào resource dữ liệu thật.

### 13.2. Hạn chế quyền của filter tự viết

Một custom `OncePerRequestFilter` có thể đọc SecurityContext nhưng phải được chèn **sau authentication filters** nếu muốn có principal đã xác thực. Nếu đặt filter trước authentication, `getAuthentication()` có thể rỗng/anonymous, không phải bug của UserDetailsService.

Nếu filter dùng để authorization thì cần đặt ở vị trí có Authentication đáng tin và xử lý `AccessDeniedException`/entry point đúng, không gọi `response.setStatus(403)` một cách tùy tiện trong mọi nhánh. Thực tế thường tốt hơn là dùng `AuthorizationManager` hoặc method security thay vì tự viết authorization filter.

### 13.3. Servlet Filter Bean và double registration

Một lỗi dễ gặp:

~~~java
@Component
class MyTraceFilter extends OncePerRequestFilter {
    // ...
}
~~~

rồi lại:

~~~java
http.addFilterAfter(
    myTraceFilter, AuthorizationFilter.class
);
~~~

Với Spring Boot, một bean kiểu `Filter` có thể được container auto-register; lại thêm vào Security chain có thể khiến nó chạy **hai lần, hai phạm vi và thứ tự không rõ**. Nếu muốn filter chỉ ở security chain, tạo instance trực tiếp hoặc dùng cách vô hiệu hóa auto-registration phù hợp (ví dụ FilterRegistrationBean disabled) rồi thêm đúng chỗ.

### 13.4. Request matching phải được kiểm thử cùng controller mappings

Spring Security và MVC dùng request matchers/mapping APIs khác nhau. Với multiple servlets, servletPath, contextPath, method, path variables, trailing slashes và framework upgrades, có thể phát sinh khác biệt. Tài liệu Spring Security hỗ trợ các request matchers phù hợp với Servlet/MVC; hãy kiểm tra theo version thực tế.

Một security route `.requestMatchers("/admin/**")` không có nghĩa interceptor `.addPathPatterns("/admin/**")` có cùng scope trong mọi ứng dụng. Bảo vệ bằng security layer và test chính những URLs/methods thật.

## 14. Quan sát và debug đúng theo thứ tự

Khi một interceptor tưởng như “không chạy”, đừng chỉnh annotation tùy ý. Hỏi:

1. Request có đến app hay bị load balancer/proxy/gateway trả trước?
2. Servlet Filter nào được container đăng ký cho URL/dispatcher?
3. `DelegatingFilterProxy`/`springSecurityFilterChain` được gọi chưa?
4. `FilterChainProxy` đã chọn SecurityFilterChain nào?
5. Authentication đã thành công hay 401?
6. `AuthorizationFilter` đã cho phép hay 403?
7. Có CSRF/CORS filter từ chối trước MVC không?
8. Request có tới `DispatcherServlet` không?
9. HandlerMapping tìm handler nào, có `HandlerMethod` không?
10. Interceptor có được đăng ký trong `WebMvcConfigurer`/MappedInterceptor đúng HandlerMapping?
11. `addPathPatterns`/`excludePathPatterns` có khớp route thực tế không?
12. Có interceptor đứng trước trả `false`?
13. Có exception làm bỏ qua `postHandle`?
14. Có async processing làm `afterConcurrentHandlingStarted` thay callback thường?
15. Request có ERROR/FORWARD dispatch, path matcher hoặc filter dispatcher registration khác?
16. MVC callback chạy nhưng response đã committed, khiến việc thêm header/body không có tác dụng?
17. Có double registration filter Bean và Security chain?
18. Có unit test chỉ gọi Controller trực tiếp hoặc `standaloneSetup` nên không tích hợp full SecurityFilterChain?

### 14.1. Bật log an toàn

Trong development có thể bật:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=DEBUG
~~~

Dùng correlation ID, path hợp lệ, selected chain, principal name được phép ghi và authorization decision. **Không log password, Authorization header, session cookies, access token, refresh token hoặc toàn bộ Authentication**.

### 14.2. Vì sao MockMvc standalone có thể đánh lừa?

`MockMvcBuilders.standaloneSetup(controller)` không tự thiết lập toàn bộ ApplicationContext, SecurityFilterChain và MVC interceptors của ứng dụng thật. Nếu test bằng standalone mà không đăng ký filters/interceptors, callback order sẽ khác.

Dùng `@SpringBootTest` và `@AutoConfigureMockMvc` như demo để request đi qua security filters và MVC infrastructure. Khi dùng `@WebMvcTest`, cần kiểm tra slice đã import SecurityConfig/interceptor nào và bổ sung cấu hình cần thiết; không khẳng định suite đã kiểm tra full stack nếu thực tế chỉ dùng một slice.

### 14.3. Test cần bổ sung khi triển khai production

- Anonymous, invalid credentials, user đúng nhưng thiếu role, admin đúng role.
- CSRF token thiếu/sai/đúng với unsafe HTTP methods.
- CORS preflight và actual cross-origin request.
- Static resources, error pages, forward routes, unmapped paths.
- Custom filter registration không bị chạy lặp.
- HandlerInterceptor `preHandle(false)` cùng thứ tự nhiều interceptors.
- Exceptions trong Controller và `afterCompletion`.
- Async handler return types và async/error redispatch.
- Resource-level ownership/tenant policy tại service.
- Multiple SecurityFilterChain matchers, servletPath và contextPath.
- Endpoint không được MVC quản lý nhưng cần security filter protection.

## 15. Những sai lầm phổ biến

### 15.1. “HandlerInterceptor là một Servlet Filter của Spring MVC”

Không. HandlerInterceptor không được container gọi như `jakarta.servlet.Filter`; nó là callback do MVC HandlerMapping/DispatcherServlet áp dụng cho handler.

### 15.2. “Tạo interceptor là đủ bảo vệ API”

Không. Nó có thể không bao phủ servlet khác, path mapping khác hoặc request bị xử lý ngoài MVC. Dùng Spring Security và phương thức authorization thích hợp.

### 15.3. “preHandle luôn chạy trước mọi security filter”

Sai. Security filters nằm trước MVC. Interceptor preHandle thường chỉ chạy **sau** khi request đi qua authentication/authorization filters.

### 15.4. “Đã 401 thì preHandle sẽ chạy và log”

Không. AuthenticationEntryPoint có thể trả 401 trước MVC. Muốn log những request đó phải instrument ở security/filter layer phù hợp.

### 15.5. “postHandle phù hợp sửa JSON sau controller”

Không đảm bảo. Với `@ResponseBody`/`ResponseEntity`, body có thể đã được ghi trong HandlerAdapter. Dùng ResponseBodyAdvice hoặc cơ chế response transformation được thiết kế phù hợp.

### 15.6. “afterCompletion luôn chạy kể cả preHandle trả false”

Không. Interceptor trả false không có afterCompletion của chính nó trong nhánh đó; các interceptors trước nó đã preHandle true có thể nhận callback.

### 15.7. “OncePerRequestFilter đúng một lần dù async/error dispatch”

Không mặc định theo mọi dispatcher scenario. Phải kiểm tra dispatch registration và hooks async/error của implementation.

### 15.8. “CsrfFilter là interceptor”

Không. Đây là một Spring Security Filter, chạy trước Controller và có thể trả 403 trước HandlerInterceptor.

### 15.9. “Filter và interceptor matching luôn giống nhau”

Không. Servlet mapping, Security RequestMatcher và MVC HandlerMapping/InterceptorRegistry có phạm vi khác nhau; test endpoints thật.

### 15.10. “Thêm custom Filter trước authentication vẫn đọc được user”

Không bảo đảm. Vị trí filter quan trọng; filter trước xác thực có thể không thấy Authentication, hoặc thấy anonymous tùy chain.

### 15.11. “Đăng ký filter là @Component rồi addFilterAfter không sao”

Có thể bị double registration, chạy ngoài chain đúng kỳ vọng. Dùng một chiến lược registration rõ ràng.

### 15.12. “Một endpoint permitAll là bypass toàn bộ security”

Không. `permitAll` là authorization decision; filters vẫn có thể thực thi. Nó khác `web.ignoring` hoặc request không match chain.

### 15.13. “SecurityContextHolder luôn có human user”

Không. Có thể anonymous hoặc service identity/JWT principal. Kiểm tra principal type và authorization policy.

### 15.14. “Interceptors bảo vệ cả @Scheduled và event listeners”

Không. Không có MVC HandlerExecutionChain ở scheduled jobs. Cần method security/job policy/service identity.

### 15.15. “Bảo vệ URL là đủ cho mọi tài nguyên”

Không. Người dùng đăng nhập hợp lệ có thể không sở hữu bản ghi. Kết hợp Spring Security request rules và service/domain resource authorization.

## 16. Câu hỏi tự đánh giá

**Câu 1.** Servlet Filter hay HandlerInterceptor chạy trước trong request thông thường?

**Đáp án:** Servlet Filter chain; Spring Security thường là một phần trong đó. MVC interceptor chạy sau khi DispatcherServlet/HandlerMapping chọn handler.

**Câu 2.** `HandlerInterceptor` có phải implementation của `jakarta.servlet.Filter` không?

**Đáp án:** Không. Nó là callback thuộc Spring MVC.

**Câu 3.** Một request thiếu Basic credentials vào `/admin/panel` có nhất thiết chạy preHandle trước khi trả 401 không?

**Đáp án:** Không. Security filter có thể từ chối trước MVC.

**Câu 4.** `preHandle` trả false thì controller có chạy không?

**Đáp án:** Không cho lần execution chain đó; interceptor phải xử lý response hợp lý.

**Câu 5.** Nếu interceptor B trả false sau khi A đã trả true, ai nhận afterCompletion?

**Đáp án:** A có thể nhận afterCompletion, còn B không nhận cho nhánh preHandle false.

**Câu 6.** Bộ lọc CSRF có thể trả 403 dù user là admin không?

**Đáp án:** Có. CSRF là protection độc lập với role authorization.

**Câu 7.** `postHandle` có luôn chỉnh được body của @ResponseBody không?

**Đáp án:** Không. Response có thể đã được ghi/commit ở HandlerAdapter.

**Câu 8.** Khi cần kiểm tra ROLE_ADMIN cho `/admin/**`, nên dùng interceptor tự đọc header hay authorizeHttpRequests?

**Đáp án:** Spring Security authorizeHttpRequests/AuthorizationFilter, kết hợp method security nếu cần.

**Câu 9.** Một MVC interceptor có bảo vệ API xử lý bởi servlet khác không?

**Đáp án:** Không tự động. Phải bảo vệ ở Servlet filter/gateway hoặc cơ chế phù hợp.

**Câu 10.** `FilterChainProxy` có cộng mọi SecurityFilterChain match vào một chain không?

**Đáp án:** Không. Nó chọn chain khớp đầu tiên.

**Câu 11.** `@Component` filter được addFilterAfter có thể tạo lỗi gì?

**Đáp án:** Double registration tại container và Security chain, khiến filter chạy lặp/đổi vị trí.

**Câu 12.** Làm sao test callback order thật trong Spring Boot?

**Đáp án:** Dùng MockMvc tích hợp SecurityFilterChain/MVC, ghi dấu từng stage vào request attribute và assert thứ tự.

**Câu 13.** `Callable` async có thể thay callback pattern không?

**Đáp án:** Có. AsyncHandlerInterceptor hỗ trợ afterConcurrentHandlingStarted; các callbacks có thể chạy lại ở ASYNC dispatch.

**Câu 14.** Tại sao interceptor không lý tưởng làm hàng rào bảo mật chính?

**Đáp án:** Vì mapping scope phụ thuộc MVC handler và có thể không đồng nhất với controller routes/servlets; security cần được áp dụng sớm hơn và rộng hơn.

**Câu 15.** Public endpoint permitAll có thể được Filter/HandlerInterceptor xử lý không?

**Đáp án:** Có. PermitAll không bypass security filters; MVC interceptor vẫn áp dụng khi handler được tìm thấy.

**Câu 16.** Nếu cần quyền đọc một invoice cụ thể của tenant A, chỉ check authenticated đủ không?

**Đáp án:** Không. Cần resource-level authorization theo owner/tenant/action ở service/domain layer.

**Câu 17.** Một REST endpoint trả 200 nhưng trace filter sau AuthorizationFilter không thấy nó, nên kiểm tra gì?

**Đáp án:** Filter registration, SecurityFilterChain matcher, dispatcher type, custom filter placement, request đã đi qua chain nào; không kết luận ngay rằng MVC interceptor không hoạt động.

**Câu 18.** Servlet Filter và MVC HandlerInterceptor có thể cùng dùng SecurityContextHolder không?

**Đáp án:** Có khi context đã được thiết lập đúng. Tuy nhiên filter trước authentication có thể chưa có principal, còn interceptor sau security thường thấy Authentication đã được nạp hoặc anonymous.

## 17. Tài liệu tham khảo chính thức

- Spring Security — **Servlet Architecture (Filter, FilterChainProxy, SecurityFilterChain)**: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security 6.5 — **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — **Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — **CSRF Protection**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — **CORS**: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — **Method Security**: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Framework 6.2 — **MVC Interception**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html
- Spring Framework 6.2 — **Configure MVC Interceptors**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html
- Spring Framework — **Servlet Filters**: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Framework — **Asynchronous MVC Requests**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework API — **HandlerInterceptor**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/HandlerInterceptor.html
- Spring Framework API — **AsyncHandlerInterceptor**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/AsyncHandlerInterceptor.html

**Ghi nhớ:** **Spring Security chạy trong Servlet Filter chain, trước DispatcherServlet; HandlerInterceptor là callback bên trong MVC sau khi tìm được handler.** Filter có thể chặn request khiến interceptor không bao giờ chạy. Dùng Spring Security để xác thực, phân quyền, CSRF/CORS và bảo vệ URL; dùng HandlerInterceptor cho cross-cutting concerns gắn với MVC handler. Chọn đúng tầng, kiểm tra rõ callback order/dispatches và bảo vệ thêm resource permissions ở service/domain layer.
